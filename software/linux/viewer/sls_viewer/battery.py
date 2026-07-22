"""System battery readout for tablet status bar.

Reads /sys/class/power_supply (type=Battery). Optional upower fallback.
Desktop hosts without a battery return present=False (gauge hidden).

Desktop layout preview (no pack):
  SLS_FAKE_BATTERY=64           # show gauge at 64%
  SLS_FAKE_BATTERY=12           # low (red)
  SLS_FAKE_BATTERY=87,charging  # blue fill + bolt
  SLS_FAKE_BATTERY=1            # same as 50% discharging
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

POWER_SUPPLY = Path("/sys/class/power_supply")
LOW_PERCENT = 15
DEFAULT_POLL_S = 5.0


@dataclass(frozen=True)
class BatteryReading:
    present: bool
    percent: Optional[int] = None  # 0–100
    charging: bool = False
    status: str = ""  # raw status string
    name: str = ""

    def status_token(self) -> str:
        """Compact token for the main bar, or empty if no battery."""
        if not self.present or self.percent is None:
            return ""
        p = max(0, min(100, int(self.percent)))
        if self.charging:
            return f"BAT {p}% ⚡"
        if p <= LOW_PERCENT:
            return f"BAT {p}%!"
        return f"BAT {p}%"


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_int(path: Path) -> Optional[int]:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _sysfs_batteries() -> List[BatteryReading]:
    if not POWER_SUPPLY.is_dir():
        return []
    out: List[BatteryReading] = []
    try:
        entries = sorted(POWER_SUPPLY.iterdir())
    except OSError:
        return []
    for entry in entries:
        typ = _read_text(entry / "type")
        if not typ or typ.lower() != "battery":
            continue
        status = (_read_text(entry / "status") or "").strip()
        percent = _read_int(entry / "capacity")
        if percent is None:
            # energy_now / energy_full
            now = _read_int(entry / "energy_now")
            full = _read_int(entry / "energy_full")
            if now is not None and full and full > 0:
                percent = int(round(100.0 * now / full))
            else:
                now = _read_int(entry / "charge_now")
                full = _read_int(entry / "charge_full")
                if now is not None and full and full > 0:
                    percent = int(round(100.0 * now / full))
        if percent is None:
            continue
        st = status.lower()
        # Bolt when charging or full on AC; plain % when discharging
        if st == "discharging":
            charging = False
        elif st in ("charging", "full", "not charging", "unknown"):
            # Full / Not charging usually means plugged in
            charging = st in ("charging", "full") or st == "not charging"
        else:
            charging = "charg" in st
        out.append(
            BatteryReading(
                present=True,
                percent=max(0, min(100, percent)),
                charging=charging,
                status=status,
                name=entry.name,
            )
        )
    return out


def _upower_fallback() -> Optional[BatteryReading]:
    upower = shutil.which("upower")
    if not upower:
        return None
    try:
        listed = subprocess.run(
            [upower, "-e"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    paths = [ln.strip() for ln in listed.stdout.splitlines() if ln.strip()]
    # Prefer DisplayDevice, then any battery path
    ordered = [p for p in paths if p.endswith("DisplayDevice")] + [
        p for p in paths if "battery" in p.lower() or "BAT" in p
    ]
    seen = set()
    for path in ordered:
        if path in seen:
            continue
        seen.add(path)
        try:
            r = subprocess.run(
                [upower, "-i", path],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except Exception:
            continue
        text = r.stdout
        if "battery" not in text.lower() and "DisplayDevice" not in path:
            continue
        # Skip pure "power supply: no"
        if "power supply:" in text and "yes" not in text.lower():
            # DisplayDevice without battery
            if "percentage:" in text and "0%" in text and "missing" in text:
                continue
        percent = None
        status = ""
        present = False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("percentage:"):
                raw = line.split(":", 1)[1].strip().replace("%", "")
                try:
                    percent = int(float(raw))
                    present = True
                except ValueError:
                    pass
            elif line.startswith("state:"):
                status = line.split(":", 1)[1].strip()
            elif line.startswith("power supply:") and "yes" in line.lower():
                present = True
        if not present or percent is None:
            continue
        # icon-name battery-missing → skip
        if "battery-missing" in text:
            continue
        st = status.lower()
        charging = st in ("charging", "fully-charged", "pending-charge")
        return BatteryReading(
            present=True,
            percent=max(0, min(100, percent)),
            charging=charging,
            status=status,
            name=path.rsplit("/", 1)[-1],
        )
    return None


def _fake_battery_from_env() -> Optional[BatteryReading]:
    """Optional desktop preview via SLS_FAKE_BATTERY (see module docstring)."""
    raw = (os.environ.get("SLS_FAKE_BATTERY") or "").strip()
    if not raw:
        return None
    # Truthy without a percent → mid pack so the widget is easy to spot
    if raw.lower() in ("1", "true", "yes", "on"):
        return BatteryReading(
            present=True,
            percent=55,
            charging=False,
            status="Fake (SLS_FAKE_BATTERY)",
            name="FAKE",
        )
    charging = False
    percent_s = raw
    if "," in raw:
        parts = [p.strip() for p in raw.split(",")]
        percent_s = parts[0]
        for p in parts[1:]:
            pl = p.lower()
            if pl in ("charging", "charge", "ac", "bolt", "1", "true", "yes"):
                charging = True
    try:
        percent = int(float(percent_s.replace("%", "")))
    except ValueError:
        return BatteryReading(
            present=True,
            percent=55,
            charging=charging,
            status="Fake (SLS_FAKE_BATTERY)",
            name="FAKE",
        )
    return BatteryReading(
        present=True,
        percent=max(0, min(100, percent)),
        charging=charging,
        status="Charging" if charging else "Discharging",
        name="FAKE",
    )


def read_battery() -> BatteryReading:
    """Best available battery reading, or present=False.

    Fake env (``SLS_FAKE_BATTERY``) wins so desktops can preview the gauge
    layout even when no pack is present.
    """
    fake = _fake_battery_from_env()
    if fake is not None:
        return fake
    bats = _sysfs_batteries()
    if bats:
        # Prefer highest capacity (main pack)
        bats.sort(key=lambda b: b.percent or 0, reverse=True)
        return bats[0]
    up = _upower_fallback()
    if up is not None:
        return up
    return BatteryReading(present=False)


class BatteryMonitor:
    """Cached battery poll for the UI tick."""

    def __init__(self, poll_s: float = DEFAULT_POLL_S):
        self.poll_s = float(poll_s)
        self._last_poll = 0.0
        self._reading = BatteryReading(present=False)

    def update(self) -> BatteryReading:
        now = time.time()
        if now - self._last_poll >= self.poll_s or self._last_poll <= 0:
            self._reading = read_battery()
            self._last_poll = now
        return self._reading

    def status_token(self) -> str:
        return self.update().status_token()
