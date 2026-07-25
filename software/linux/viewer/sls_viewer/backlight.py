"""Display brightness for Settings (tablet backlight + desktop fallbacks).

Order of backends:
  1) /sys/class/backlight (real panel backlight — typical tablets/laptops)
  2) brightnessctl (if installed and permitted)
  3) xrandr --brightness (software gamma on the primary output — desktop/HDMI)

Desktop towers with only HDMI often have no sysfs backlight; xrandr may still
dim the image. Tablets usually use (1).

Notes for Cherry Trail / RCA tablets:
  - Prefer intel_backlight (etc.) over acpi_video0 — alphabetical order alone
    often picks a dead ACPI node first.
  - brightness sysfs is often root-only until udev grants video-group write
    (appliance: 99-sls-backlight.rules). Read-only sysfs must not disable ±
    if brightnessctl or xrandr can still set.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

BACKLIGHT_ROOT = Path("/sys/class/backlight")
# Field UI: 5% steps, never full blackout, leave a little headroom at the top (#24)
MIN_PERCENT = 5
MAX_PERCENT = 95
DEFAULT_STEP = 5


@dataclass
class BrightnessInfo:
    available: bool
    percent: Optional[int] = None  # 0–100 (we clamp to MIN–MAX on set)
    backend: str = ""  # sysfs name, brightnessctl, xrandr:HDMI-1, …
    writable: bool = False
    detail: str = ""  # human note / error


def _read_int(path: Path) -> Optional[int]:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _write_int(path: Path, value: int) -> bool:
    try:
        path.write_text(str(int(value)), encoding="utf-8")
        return True
    except OSError:
        return False


def _sysfs_rank(name: str) -> int:
    """Lower = preferred. Avoid acpi_video* when a real DRM backlight exists."""
    n = name.lower()
    if n == "intel_backlight" or n.startswith("intel_backlight"):
        return 0
    if "amdgpu" in n or n.startswith("nvidia") or "gmux" in n:
        return 1
    if n.startswith("acpi_video") or n.startswith("acpi_"):
        return 50
    return 10


def _sysfs_devices() -> List[Path]:
    if not BACKLIGHT_ROOT.is_dir():
        return []
    try:
        devs = [p for p in BACKLIGHT_ROOT.iterdir() if p.is_dir()]
    except OSError:
        return []
    return sorted(devs, key=lambda p: (_sysfs_rank(p.name), p.name))


def _sysfs_pick() -> Optional[Path]:
    for dev in _sysfs_devices():
        mx = _read_int(dev / "max_brightness")
        cur = _read_int(dev / "brightness")
        if mx is not None and mx > 0 and cur is not None:
            return dev
    return None


def _sysfs_read() -> Optional[BrightnessInfo]:
    dev = _sysfs_pick()
    if dev is None:
        return None
    mx = _read_int(dev / "max_brightness")
    cur = _read_int(dev / "brightness")
    if mx is None or mx <= 0 or cur is None:
        return None
    pct = int(round(100.0 * cur / mx))
    bpath = dev / "brightness"
    writable = os.access(bpath, os.W_OK)
    return BrightnessInfo(
        available=True,
        percent=max(0, min(100, pct)),
        backend=f"sysfs:{dev.name}",
        writable=writable,
        detail="" if writable else "backlight read-only (need video group / udev)",
    )


def _sysfs_set(percent: int) -> Optional[BrightnessInfo]:
    # Try preferred device first, then any other writable node
    tried: List[str] = []
    for dev in _sysfs_devices():
        mx = _read_int(dev / "max_brightness")
        if mx is None or mx <= 0:
            continue
        bpath = dev / "brightness"
        if not os.access(bpath, os.W_OK):
            tried.append(f"{dev.name}:ro")
            continue
        raw = max(1, min(mx, int(round(mx * percent / 100.0))))
        if _write_int(bpath, raw):
            # Re-read from the device we wrote (not a re-pick that might differ)
            cur = _read_int(bpath)
            pct = int(round(100.0 * (cur if cur is not None else raw) / mx))
            return BrightnessInfo(
                available=True,
                percent=max(0, min(100, pct)),
                backend=f"sysfs:{dev.name}",
                writable=True,
                detail="",
            )
        tried.append(f"{dev.name}:fail")
    if tried:
        return BrightnessInfo(
            available=True,
            percent=None,
            backend="sysfs",
            writable=False,
            detail="write failed (permission): " + ",".join(tried)[:60],
        )
    return None


def _brightnessctl_read() -> Optional[BrightnessInfo]:
    exe = shutil.which("brightnessctl")
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, "g"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        # "50%" or "Device 'intel_backlight' … Current brightness: 400 (50%)"
        text = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"\((\d+)%\)", text) or re.search(r"(\d+)%", text)
        if not m:
            # try info
            r2 = subprocess.run(
                [exe, "i"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            text = r2.stdout or ""
            m = re.search(r"\((\d+)%\)", text)
        if not m:
            return None
        pct = int(m.group(1))
        return BrightnessInfo(
            available=True,
            percent=max(0, min(100, pct)),
            backend="brightnessctl",
            writable=True,
            detail="",
        )
    except Exception:
        return None


def _brightnessctl_set(percent: int) -> Optional[BrightnessInfo]:
    exe = shutil.which("brightnessctl")
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, "s", f"{int(percent)}%"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if r.returncode != 0:
            return BrightnessInfo(
                available=True,
                percent=None,
                backend="brightnessctl",
                writable=False,
                detail=(r.stderr or r.stdout or "brightnessctl failed")[:80],
            )
        return _brightnessctl_read()
    except Exception as e:
        return BrightnessInfo(
            available=False, detail=str(e)[:80]
        )


def _xrandr_primary() -> Optional[str]:
    exe = shutil.which("xrandr")
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, "--query"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    primary = None
    first_conn = None
    for line in r.stdout.splitlines():
        # "HDMI-1 connected primary 1920x1080+0+0 ..."
        if " connected" not in line:
            continue
        name = line.split()[0]
        if first_conn is None:
            first_conn = name
        if " primary" in line:
            primary = name
            break
    return primary or first_conn


def _can_software_or_bctl() -> bool:
    if shutil.which("brightnessctl"):
        return True
    return bool(_xrandr_primary())


# Soft-brightness via xrandr (not hardware backlight). Keep last set value.
_xrandr_percent: Optional[int] = None


def _xrandr_read() -> Optional[BrightnessInfo]:
    global _xrandr_percent
    out = _xrandr_primary()
    if not out:
        return None
    # xrandr doesn't report software brightness reliably; use last set or 100
    pct = _xrandr_percent if _xrandr_percent is not None else 100
    return BrightnessInfo(
        available=True,
        percent=pct,
        backend=f"xrandr:{out}",
        writable=True,
        detail="software brightness (HDMI/desktop)",
    )


def _xrandr_set(percent: int) -> Optional[BrightnessInfo]:
    global _xrandr_percent
    exe = shutil.which("xrandr")
    out = _xrandr_primary()
    if not exe or not out:
        return None
    # Map 5–100% → 0.05–1.0 (avoid total black)
    level = max(0.05, min(1.0, percent / 100.0))
    try:
        r = subprocess.run(
            [exe, "--output", out, "--brightness", f"{level:.3f}"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if r.returncode != 0:
            return BrightnessInfo(
                available=True,
                percent=_xrandr_percent,
                backend=f"xrandr:{out}",
                writable=False,
                detail=(r.stderr or "xrandr failed")[:80],
            )
        _xrandr_percent = int(percent)
        return BrightnessInfo(
            available=True,
            percent=_xrandr_percent,
            backend=f"xrandr:{out}",
            writable=True,
            detail="software brightness (HDMI/desktop)",
        )
    except Exception as e:
        return BrightnessInfo(available=False, detail=str(e)[:80])


def get_brightness() -> BrightnessInfo:
    """Current brightness, or available=False if nothing works.

    If sysfs is readable but not writable, still mark writable=True when
    brightnessctl or xrandr can set — otherwise Settings greys out ±.
    """
    sys_info = _sysfs_read()
    if sys_info is not None and sys_info.writable:
        return sys_info

    bctl = _brightnessctl_read()
    if bctl is not None:
        return bctl

    if sys_info is not None:
        if _can_software_or_bctl():
            how = (
                "brightnessctl/xrandr"
                if shutil.which("brightnessctl")
                else "xrandr software"
            )
            return BrightnessInfo(
                available=True,
                percent=sys_info.percent,
                backend=sys_info.backend,
                writable=True,
                detail=f"sysfs read-only; set via {how}",
            )
        return sys_info

    xr = _xrandr_read()
    if xr is not None:
        return xr
    return BrightnessInfo(
        available=False,
        detail="no backlight or xrandr control found",
    )


def set_brightness_percent(percent: int) -> BrightnessInfo:
    """Set brightness 5–95% in field steps. Tries sysfs → brightnessctl → xrandr."""
    percent = int(max(MIN_PERCENT, min(MAX_PERCENT, percent)))
    # Always try sysfs write (may work even if access() lied after udev)
    got = _sysfs_set(percent)
    if got is not None and got.writable and got.percent is not None:
        return got
    if shutil.which("brightnessctl"):
        got = _brightnessctl_set(percent)
        if got is not None and got.available and got.percent is not None:
            return got
    # Desktop / HDMI / last-resort software dim on panel
    got = _xrandr_set(percent)
    if got is not None and got.available and got.writable:
        return got
    # Last resort: report best read-only info
    cur = get_brightness()
    if cur.available:
        return BrightnessInfo(
            available=True,
            percent=cur.percent,
            backend=cur.backend,
            writable=False,
            detail=cur.detail or "could not change brightness",
        )
    return BrightnessInfo(
        available=False,
        detail="could not set brightness on this hardware",
    )


def nudge_brightness(delta_percent: int) -> BrightnessInfo:
    cur = get_brightness()
    if not cur.available:
        return cur
    base = cur.percent if cur.percent is not None else 100
    return set_brightness_percent(base + int(delta_percent))


def apply_persisted_percent(percent: Optional[int]) -> BrightnessInfo:
    """Apply saved preference if any (call once at app start)."""
    if percent is None:
        return get_brightness()
    return set_brightness_percent(int(percent))
