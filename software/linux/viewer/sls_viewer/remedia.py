"""Detect writable removable volumes (USB sticks + SD cards) for captures.

USB pen drives and tablet SD cards usually appear as:
  - /media/$USER/<Label>
  - /run/media/$USER/<Label>
lsblk marks USB as RM/HOTPLUG; SD often as mmcblk* (RM may be 0).

We combine mount-path heuristics with lsblk so both pen drives and SD work.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Set

# Subfolder on external media (keeps root of stick tidy)
CAPTURES_SUBDIR = "sls-captures"

# Filesystems we are willing to write investigation media on
_OK_FS = frozenset(
    {
        "vfat",
        "exfat",
        "ntfs",
        "ntfs3",
        "ext4",
        "ext3",
        "ext2",
        "btrfs",
        "xfs",
        "fuseblk",  # often NTFS via ntfs-3g
        "fuse.exfat",
    }
)


@dataclass(frozen=True)
class MediaVolume:
    path: Path
    label: str
    kind: str  # "usb" | "sd" | "removable" | "other"
    free_bytes: int = 0
    source: str = ""  # e.g. /dev/sdb1 or /dev/mmcblk0p1

    def captures_path(self) -> Path:
        return self.path / CAPTURES_SUBDIR

    def short_label(self) -> str:
        free = ""
        if self.free_bytes > 0:
            gib = self.free_bytes / (1024**3)
            if gib >= 1:
                free = f" · {gib:.1f}G free"
            else:
                free = f" · {self.free_bytes / (1024**2):.0f}M free"
        return f"{self.kind.upper()}:{self.label}{free}"


def _user_media_roots() -> List[Path]:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    home = Path.home()
    roots: List[Path] = []
    for p in (
        Path("/media") / user if user else None,
        Path("/run/media") / user if user else None,
        Path("/media"),
        Path("/run/media"),
        home / "media",
    ):
        if p is None:
            continue
        if p.is_dir():
            roots.append(p)
    return roots


def _is_probably_system_mount(path: Path) -> bool:
    s = str(path.resolve()) if path.exists() else str(path)
    # Never treat OS root or home itself as "removable capture media"
    if s in ("/", "/home", str(Path.home())):
        return True
    if s.startswith("/boot") or s.startswith("/snap"):
        return True
    if s in ("/media", "/run/media"):
        return True
    return False


def _classify_device(name: str, rm: bool, hotplug: bool) -> str:
    n = (name or "").lower()
    if n.startswith("mmcblk") or "mmc" in n:
        return "sd"
    if n.startswith("sd") and (rm or hotplug):
        return "usb"
    if rm or hotplug:
        return "removable"
    return "other"


def _writable_dir(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
        return os.access(path, os.W_OK | os.X_OK)
    except OSError:
        return False


def _free_bytes(path: Path) -> int:
    try:
        u = shutil.disk_usage(path)
        return int(u.free)
    except OSError:
        return 0


def _from_lsblk() -> List[MediaVolume]:
    """Parse lsblk JSON for mounted removable / SD partitions."""
    lsblk = shutil.which("lsblk")
    if not lsblk:
        return []
    try:
        r = subprocess.run(
            [
                lsblk,
                "-J",
                "-b",
                "-o",
                "NAME,MOUNTPOINT,RM,HOTPLUG,LABEL,TYPE,FSTYPE,SIZE",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return []
    if r.returncode != 0 or not r.stdout.strip():
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []

    out: List[MediaVolume] = []

    def walk(nodes: Sequence[dict], parent_name: str = "") -> None:
        for node in nodes or []:
            name = str(node.get("name") or parent_name)
            children = node.get("children") or []
            mnt = node.get("mountpoint")
            typ = (node.get("type") or "").lower()
            fstype = (node.get("fstype") or "").lower()
            rm = bool(int(node.get("rm") or 0))
            hot = bool(int(node.get("hotplug") or 0))
            label = (node.get("label") or name or "media").strip() or name

            if mnt and typ in ("part", "disk", "crypt", "lvm"):
                path = Path(mnt)
                if (
                    not _is_probably_system_mount(path)
                    and _writable_dir(path)
                    and (not fstype or fstype in _OK_FS or fstype.startswith("fuse"))
                ):
                    kind = _classify_device(name, rm, hot)
                    # Prefer classifying only removable-ish, but include mmc even if RM=0
                    if kind != "other" or name.startswith("mmcblk"):
                        if kind == "other" and name.startswith("mmcblk"):
                            kind = "sd"
                        if kind != "other":
                            out.append(
                                MediaVolume(
                                    path=path,
                                    label=label,
                                    kind=kind,
                                    free_bytes=_free_bytes(path),
                                    source=f"/dev/{name}",
                                )
                            )
            if children:
                walk(children, name)

    walk(data.get("blockdevices") or [])
    return out


def _from_media_dirs() -> List[MediaVolume]:
    """Scan desktop automount locations (works when lsblk JSON is incomplete)."""
    out: List[MediaVolume] = []
    seen: Set[str] = set()
    for root in _user_media_roots():
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            # /media/user or /run/media/user → mount is one level down
            # /media itself might contain user dirs — recurse one level if not writable
            candidates = [entry]
            if not _writable_dir(entry):
                try:
                    candidates = [c for c in entry.iterdir() if c.is_dir()]
                except OSError:
                    candidates = []
            for path in candidates:
                try:
                    key = str(path.resolve())
                except OSError:
                    key = str(path)
                if key in seen or _is_probably_system_mount(path):
                    continue
                if not _writable_dir(path):
                    continue
                seen.add(key)
                # Heuristic kind from path name
                low = path.name.lower()
                kind = "removable"
                if "sd" in low or "mmc" in low:
                    kind = "sd"
                elif "usb" in low or "pendrive" in low:
                    kind = "usb"
                out.append(
                    MediaVolume(
                        path=path,
                        label=path.name,
                        kind=kind,
                        free_bytes=_free_bytes(path),
                        source="",
                    )
                )
    return out


def list_removable_volumes() -> List[MediaVolume]:
    """Return unique writable removable/SD volumes, largest free space first."""
    by_path: dict[str, MediaVolume] = {}
    for vol in _from_lsblk() + _from_media_dirs():
        try:
            key = str(vol.path.resolve())
        except OSError:
            key = str(vol.path)
        if key not in by_path or vol.free_bytes > by_path[key].free_bytes:
            by_path[key] = vol
    vols = list(by_path.values())
    # Prefer SD then USB then other; then free space
    order = {"sd": 0, "usb": 1, "removable": 2, "other": 3}
    vols.sort(key=lambda v: (order.get(v.kind, 9), -v.free_bytes, v.label.lower()))
    return vols


def pick_auto_volume(
    volumes: Optional[List[MediaVolume]] = None,
) -> Optional[MediaVolume]:
    """Best volume for auto mode: first SD, else first USB/removable."""
    vols = volumes if volumes is not None else list_removable_volumes()
    if not vols:
        return None
    for v in vols:
        if v.kind == "sd":
            return v
    return vols[0]


def ensure_captures_on_volume(vol: MediaVolume) -> Optional[Path]:
    """Create sls-captures/ on volume; return path or None if not writable."""
    dest = vol.captures_path()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        if not _writable_dir(dest):
            return None
        # probe write
        probe = dest / ".sls_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return dest
    except OSError:
        return None


def copy_local_to_media(
    local_dir: Path,
    media_captures_dir: Path,
) -> tuple[int, int]:
    """
    Copy files from local captures into media sls-captures/.

    Skips files that already exist with the same name and size.
    Returns (copied, skipped).
    """
    local_dir = Path(local_dir)
    media_captures_dir = Path(media_captures_dir)
    media_captures_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    if not local_dir.is_dir():
        return 0, 0
    for src in sorted(local_dir.iterdir()):
        if not src.is_file():
            continue
        # skip hidden / probe files
        if src.name.startswith("."):
            continue
        dst = media_captures_dir / src.name
        try:
            if dst.is_file() and dst.stat().st_size == src.stat().st_size:
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
        except OSError:
            pass
    return copied, skipped


def resolve_captures_dir(
    mode: str,
    local_dir: Path,
    *,
    preferred_mount: str = "",
) -> tuple[Path, str]:
    """
    Resolve captures directory.

    mode:
      - local: always local_dir
      - auto:  removable/SD if present else local_dir

    Returns (path, status_token) e.g. ("…/sls-captures", "SD:NIKON · 12G free")
    """
    mode = (mode or "local").lower().strip()
    local_dir = Path(local_dir)

    if mode != "auto":
        try:
            local_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return local_dir, "local"

    vols = list_removable_volumes()
    chosen: Optional[MediaVolume] = None
    if preferred_mount:
        pref = Path(preferred_mount)
        for v in vols:
            try:
                if v.path.resolve() == pref.resolve():
                    chosen = v
                    break
            except OSError:
                if v.path == pref:
                    chosen = v
                    break
    if chosen is None:
        chosen = pick_auto_volume(vols)

    if chosen is not None:
        dest = ensure_captures_on_volume(chosen)
        if dest is not None:
            return dest, chosen.short_label()

    try:
        local_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return local_dir, "local (no media)"
