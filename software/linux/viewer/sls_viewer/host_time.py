"""System date/time for field Settings (#11).

Operators set local clock without a desktop applet (kiosk tablets, no NTP).

Apply path (same spirit as format-media / poweroff):
  1. ``timedatectl --no-ask-password …``  (polkit passwordless for user ``sls``)
  2. ``pkexec timedatectl …``
  3. ``sudo -n timedatectl …``  (sudoers.d/sls-timedate)

Firmware: polkit rule + optional sudoers — see
software/linux/docs/DATE-TIME-PRIVS.md and FOR-FIRMWARE-TEAM.md.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

# Common US + UTC first (field fleet); operators can cycle these without a full TZ list.
COMMON_TIMEZONES: Tuple[str, ...] = (
    "America/Los_Angeles",
    "America/Denver",
    "America/Phoenix",
    "America/Chicago",
    "America/New_York",
    "America/Anchorage",
    "Pacific/Honolulu",
    "UTC",
    "America/Toronto",
    "America/Vancouver",
    "Europe/London",
)

_PRIV_HINT = (
    "need timedatectl privilege — install firmware polkit rule "
    "org.freedesktop.timedate1.* for user sls, or sudoers.d/sls-timedate"
)


@dataclass(frozen=True)
class HostTimeInfo:
    """Snapshot of host clock (best-effort)."""

    local: datetime
    timezone: str
    ntp: Optional[bool] = None
    ntp_synchronized: Optional[bool] = None
    detail: str = ""

    def local_str(self) -> str:
        return self.local.strftime("%Y-%m-%d %H:%M:%S")

    def summary(self) -> str:
        ntp = (
            "NTP on"
            if self.ntp is True
            else "NTP off"
            if self.ntp is False
            else "NTP ?"
        )
        sync = ""
        if self.ntp_synchronized is True:
            sync = " · synced"
        elif self.ntp_synchronized is False:
            sync = " · not synced"
        return f"{self.local_str()}  ·  {self.timezone}  ·  {ntp}{sync}"


def _run(cmd: Sequence[str], timeout: int = 15) -> Tuple[int, str]:
    try:
        r = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return int(r.returncode), out.strip()
    except FileNotFoundError:
        return 127, "command not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as e:
        return 1, str(e)


def _timedatectl_bin() -> Optional[str]:
    return shutil.which("timedatectl") or (
        "/usr/bin/timedatectl" if os.path.isfile("/usr/bin/timedatectl") else None
    )


def _parse_bool(raw: str) -> Optional[bool]:
    s = (raw or "").strip().lower()
    if s in ("yes", "true", "1", "on", "active"):
        return True
    if s in ("no", "false", "0", "off", "inactive"):
        return False
    return None


def read_host_time() -> HostTimeInfo:
    """Return current local wall clock + timezone / NTP flags when available."""
    now = datetime.now().replace(microsecond=0)
    tz = ""
    ntp: Optional[bool] = None
    ntp_sync: Optional[bool] = None
    detail_parts: List[str] = []

    # Prefer zoneinfo name when present
    try:
        if now.tzinfo is not None:
            tz = str(now.tzinfo)
    except Exception:
        pass

    bin_path = _timedatectl_bin()
    if bin_path:
        code, out = _run(
            [
                bin_path,
                "show",
                "-p",
                "Timezone",
                "-p",
                "NTP",
                "-p",
                "NTPSynchronized",
                "--value",
            ],
            timeout=5,
        )
        if code == 0 and out:
            lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
            # timedatectl --value prints one property per line in request order
            if len(lines) >= 1:
                tz = lines[0] or tz
            if len(lines) >= 2:
                ntp = _parse_bool(lines[1])
            if len(lines) >= 3:
                ntp_sync = _parse_bool(lines[2])
        else:
            # Fallback: parse `timedatectl status`
            code2, st = _run([bin_path, "status"], timeout=5)
            if code2 == 0:
                m = re.search(r"Time zone:\s*(\S+)", st)
                if m:
                    tz = m.group(1)
                m = re.search(r"NTP service:\s*(\S+)", st, re.I)
                if m:
                    ntp = _parse_bool(m.group(1))
                m = re.search(r"System clock synchronized:\s*(\S+)", st, re.I)
                if m:
                    ntp_sync = _parse_bool(m.group(1))
            elif code != 0:
                detail_parts.append(out[:120] or f"timedatectl exit {code}")

    if not tz:
        # /etc/localtime symlink → zoneinfo path
        try:
            link = os.path.realpath("/etc/localtime")
            marker = "/zoneinfo/"
            if marker in link:
                tz = link.split(marker, 1)[1]
        except OSError:
            pass
    if not tz:
        tz = "local"

    return HostTimeInfo(
        local=now,
        timezone=tz,
        ntp=ntp,
        ntp_synchronized=ntp_sync,
        detail="; ".join(detail_parts),
    )


def next_common_timezone(current: str) -> str:
    """Cycle through COMMON_TIMEZONES (or start at first if unknown)."""
    cur = (current or "").strip()
    zones = list(COMMON_TIMEZONES)
    if cur in zones:
        return zones[(zones.index(cur) + 1) % len(zones)]
    # If current is a known zone not in list, keep it then jump to first common
    return zones[0]


def _privileged_timedatectl(args: Sequence[str], timeout: int = 20) -> Tuple[int, str, str]:
    """Run timedatectl with escalating privilege. Returns (code, output, method)."""
    bin_path = _timedatectl_bin()
    if not bin_path:
        return 127, "timedatectl not found (install systemd)", "none"

    attempts: List[Tuple[str, List[str]]] = [
        ("timedatectl", [bin_path, "--no-ask-password", *args]),
        ("pkexec", ["pkexec", bin_path, *args]),
        ("sudo", ["sudo", "-n", bin_path, *args]),
    ]
    # Root already: direct without --no-ask-password noise
    if os.geteuid() == 0:
        attempts = [("root", [bin_path, *args])]

    last_out = ""
    for method, cmd in attempts:
        code, out = _run(cmd, timeout=timeout)
        last_out = out
        if code == 0:
            return 0, out, method
        # Permission-ish failures → try next method
        low = (out or "").lower()
        if any(
            k in low
            for k in (
                "auth",
                "permission",
                "not authorized",
                "interactive authentication",
                "password",
                "polkit",
                "a password is required",
            )
        ):
            continue
        if code in (1, 126, 127) and method != attempts[-1][0]:
            # try next on generic failure from no-ask-password
            if "ask-password" in low or "auth" in low or code != 0:
                continue
        # Non-auth failure from first successful-looking path: still try others
        # for set-time when polkit denies silently
        if method != attempts[-1][0]:
            continue
    return 1, last_out or _PRIV_HINT, "failed"


def set_host_timezone(zone: str) -> Tuple[bool, str]:
    """Set system timezone (e.g. America/Los_Angeles)."""
    z = (zone or "").strip()
    if not z or "/" not in z and z.upper() != "UTC":
        # Allow bare UTC; reject empty / junk
        if z.upper() != "UTC":
            return False, f"invalid timezone: {zone!r}"
        z = "UTC"
    code, out, method = _privileged_timedatectl(["set-timezone", z])
    if code == 0:
        return True, f"timezone → {z} (via {method})"
    msg = out or _PRIV_HINT
    return False, f"set-timezone failed: {msg}"


def set_host_time(when: datetime) -> Tuple[bool, str]:
    """Set system local wall clock to ``when`` (naive local or aware).

    Turns NTP off first when active so the set sticks on offline field units.
    """
    if when.tzinfo is not None:
        # Convert to local naive for timedatectl local interpretation
        local = when.astimezone().replace(tzinfo=None)
    else:
        local = when.replace(microsecond=0)

    # Disable NTP so manual set is not immediately overwritten
    info = read_host_time()
    ntp_note = ""
    if info.ntp is True:
        c, o, m = _privileged_timedatectl(["set-ntp", "false"])
        if c != 0:
            # Continue anyway — some systems allow set-time while NTP is on
            ntp_note = f" (NTP still on; set-ntp failed: {o[:80]})"
        else:
            ntp_note = f" (NTP off via {m})"

    stamp = local.strftime("%Y-%m-%d %H:%M:%S")
    code, out, method = _privileged_timedatectl(["set-time", stamp])
    if code == 0:
        return True, f"time → {stamp} (via {method}){ntp_note}"
    msg = out or _PRIV_HINT
    # Helpful hint when privilege missing
    if any(
        k in msg.lower()
        for k in ("auth", "permission", "password", "polkit", "not authorized")
    ):
        msg = f"{msg} — {_PRIV_HINT}"
    return False, f"set-time failed: {msg}{ntp_note}"
