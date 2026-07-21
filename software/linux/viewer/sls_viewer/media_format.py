"""Prepare / format removable media for SLS captures (issue #8).

v1 safety model:
  - Only volumes from remedia.list_removable_volumes() (USB/SD, mounted, writable)
  - Refuse system mounts, nvme, disks > 128 GiB
  - **Prepare** (no root): ensure ``sls-captures/`` on the mounted volume
  - **Format** (needs privileges): reformat the **mounted partition** as FAT32
    label ``SLS-MEDIA``, remount, create ``sls-captures/``

Full-disk wipe of a whole USB (like firmware prep-sls-media-usb.sh) stays a
host script — app only formats the data partition currently mounted.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .remedia import (
    CAPTURES_SUBDIR,
    MediaVolume,
    ensure_captures_on_volume,
    list_removable_volumes,
)

# Match firmware prep-sls-media-usb.sh
DEFAULT_LABEL = "SLS-MEDIA"
MAX_FORMAT_BYTES = 128 * 1024 * 1024 * 1024  # 128 GiB


@dataclass
class FormatResult:
    ok: bool
    message: str
    volume: Optional[MediaVolume] = None


def _is_safe_device_node(dev: str) -> bool:
    if not dev or not dev.startswith("/dev/"):
        return False
    base = os.path.basename(dev)
    # partitions: sdb1, mmcblk0p1 — not bare nvme, not whole multi-TB disks by name alone
    if "nvme" in base:
        return False
    if base.startswith("loop") or base.startswith("dm-") or base.startswith("sr"):
        return False
    # Prefer partition nodes for format (safer than whole disk in app v1)
    if re.match(r"^sd[a-z]+\d+$", base):
        return True
    if re.match(r"^mmcblk\d+p\d+$", base):
        return True
    # whole-disk sdX only if removable (caller also checks size)
    if re.match(r"^sd[a-z]+$", base):
        return True
    if re.match(r"^mmcblk\d+$", base):
        return True
    return False


def device_size_bytes(dev: str) -> int:
    try:
        r = subprocess.run(
            ["lsblk", "-nb", "-o", "SIZE", dev],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().splitlines()[0])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return 0


def _is_removable_sysfs(dev: str) -> bool:
    base = os.path.basename(dev)
    # partition → parent disk
    disk = re.sub(r"p?\d+$", "", base) if base.startswith("mmcblk") else re.sub(r"\d+$", "", base)
    if base.startswith("mmcblk"):
        # mmcblk0p1 → mmcblk0
        m = re.match(r"(mmcblk\d+)", base)
        disk = m.group(1) if m else base
    path = Path(f"/sys/block/{disk}/removable")
    try:
        if path.is_file() and path.read_text(encoding="utf-8").strip() == "1":
            return True
    except OSError:
        pass
    # SD often RM=0
    if base.startswith("mmcblk"):
        return True
    # udev bus=usb
    try:
        r = subprocess.run(
            ["udevadm", "info", "-q", "property", "-n", f"/dev/{disk}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if "ID_BUS=usb" in (r.stdout or ""):
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False


def validate_format_candidate(vol: MediaVolume) -> Tuple[bool, str]:
    """Return (ok, reason). ok=False means refuse format."""
    if vol.kind not in ("usb", "sd", "removable"):
        return False, f"refusing kind={vol.kind}"
    try:
        resolved = str(vol.path.resolve())
    except OSError:
        resolved = str(vol.path)
    if resolved in ("/", "/home", str(Path.home())):
        return False, "refusing system path"
    if resolved.startswith("/boot") or resolved.startswith("/snap"):
        return False, "refusing system path"
    dev = (vol.source or "").strip()
    if not dev:
        return False, "no block device for this mount (cannot format safely)"
    if not _is_safe_device_node(dev):
        return False, f"unsafe device node: {dev}"
    if not Path(dev).is_block_device():
        return False, f"not a block device: {dev}"
    if not _is_removable_sysfs(dev):
        return False, f"not removable/USB/SD: {dev}"
    size = device_size_bytes(dev)
    if size <= 0:
        return False, f"could not read size of {dev}"
    if size > MAX_FORMAT_BYTES:
        return False, f"{dev} larger than 128 GiB — refusing"
    return True, "ok"


def prepare_captures_folder(vol: Optional[MediaVolume] = None) -> FormatResult:
    """No-root: ensure sls-captures/ on current auto volume (or given vol)."""
    if vol is None:
        vols = list_removable_volumes()
        if not vols:
            return FormatResult(False, "No USB/SD mounted")
        vol = vols[0]
    dest = ensure_captures_on_volume(vol)
    if dest is None:
        return FormatResult(False, f"Cannot write {vol.path / CAPTURES_SUBDIR}", vol)
    return FormatResult(
        True,
        f"Ready: {dest} ({vol.short_label()})",
        vol,
    )


def _run(cmd: Sequence[str], timeout: int = 120) -> Tuple[int, str]:
    try:
        r = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return int(r.returncode), out[-500:] if out else ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _privileged(cmd: Sequence[str], timeout: int = 180) -> Tuple[int, str]:
    """Run with pkexec or sudo -n (never prompts interactively if neither works)."""
    if os.geteuid() == 0:
        return _run(cmd, timeout=timeout)
    if shutil.which("pkexec"):
        return _run(["pkexec", *cmd], timeout=timeout)
    if shutil.which("sudo"):
        return _run(["sudo", "-n", *cmd], timeout=timeout)
    return 1, "need root (pkexec or passwordless sudo) to format"


def format_volume_fat32(
    vol: MediaVolume,
    *,
    label: str = DEFAULT_LABEL,
) -> FormatResult:
    """
    Format the volume's block device as FAT32, remount, create sls-captures/.

    Destroys all data on that partition. Caller must confirm with the operator.
    """
    ok, reason = validate_format_candidate(vol)
    if not ok:
        return FormatResult(False, reason, vol)

    dev = vol.source.strip()
    label = re.sub(r"[^A-Za-z0-9_-]", "", label or DEFAULT_LABEL)[:11] or DEFAULT_LABEL
    mountpoint = str(vol.path)

    # Unmount
    _run(["udisksctl", "unmount", "-b", dev], timeout=30)
    _run(["umount", mountpoint], timeout=30)
    _run(["umount", dev], timeout=30)
    time.sleep(0.5)

    mkfs = shutil.which("mkfs.vfat") or shutil.which("mkfs.fat")
    if not mkfs:
        return FormatResult(
            False,
            "mkfs.vfat not found (install dosfstools)",
            vol,
        )

    # -I allows formatting whole-disk if we ever pass one; partitions are normal
    rc, out = _privileged([mkfs, "-F", "32", "-n", label, "-I", dev], timeout=180)
    if rc != 0:
        return FormatResult(False, f"mkfs failed: {out or rc}", vol)

    # Remount
    new_mount = ""
    rc_m, out_m = _run(["udisksctl", "mount", "-b", dev], timeout=30)
    if rc_m == 0 and out_m:
        # "Mounted /dev/sdb1 at /media/user/SLS-MEDIA"
        m = re.search(r"at\s+(\S+)\s*$", out_m, re.MULTILINE)
        if m:
            new_mount = m.group(1).rstrip(".")
    if not new_mount:
        # fallback: wait for automount under /media
        time.sleep(1.5)
        for cand in list_removable_volumes():
            if cand.source == dev or label.lower() in cand.label.lower():
                new_mount = str(cand.path)
                break
    if not new_mount:
        return FormatResult(
            False,
            f"formatted {dev} but remount failed — plug cycle stick; {out_m}",
            vol,
        )

    new_vol = MediaVolume(
        path=Path(new_mount),
        label=label,
        kind=vol.kind,
        free_bytes=0,
        source=dev,
    )
    dest = ensure_captures_on_volume(new_vol)
    if dest is None:
        return FormatResult(
            False,
            f"formatted + mounted at {new_mount} but could not create {CAPTURES_SUBDIR}",
            new_vol,
        )
    return FormatResult(
        True,
        f"Formatted {dev} as FAT32 «{label}»; {dest}",
        new_vol,
    )


def list_format_candidates() -> List[Tuple[MediaVolume, bool, str]]:
    """All removable mounts with (vol, can_format, reason)."""
    rows: List[Tuple[MediaVolume, bool, str]] = []
    for vol in list_removable_volumes():
        ok, reason = validate_format_candidate(vol)
        rows.append((vol, ok, reason))
    return rows
