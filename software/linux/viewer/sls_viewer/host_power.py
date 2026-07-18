"""Host power-off helpers for appliance Quit (issue #4).

Exit-code contract (firmware launcher + app):
  0  — clean quit to desktop / shell
  10 — operator requested host power-off
  11 — relaunch app (kiosk; reserved)

When Settings “Power off on Quit” is ON (or SLS_QUIT_ACTION=shutdown),
the app exits with code 10 and best-effort requests poweroff so:
  - appliance launcher can honor the code without a shell fallback, and
  - standalone field installs still power off when sudoers/polkit allow it.
"""

from __future__ import annotations

import os
import subprocess
from typing import List, Sequence

# Match sls-camera-firmware overlay/usr/local/bin/sls-camera
EXIT_OK = 0
EXIT_POWEROFF = 10
EXIT_RELAUNCH = 11

_SHUTDOWN_ENV = frozenset({"shutdown", "poweroff", "off", "1", "true", "yes"})
_EXIT_ENV = frozenset({"exit", "desktop", "none", "0", "false", "no"})


def env_wants_poweroff_on_quit() -> bool | None:
    """Return True/False if SLS_QUIT_ACTION forces a mode; None if unset."""
    raw = (os.environ.get("SLS_QUIT_ACTION") or "").strip().lower()
    if not raw:
        return None
    if raw in _SHUTDOWN_ENV:
        return True
    if raw in _EXIT_ENV:
        return False
    return None


def request_host_poweroff() -> bool:
    """Best-effort host power-off. Returns True if a command appeared to succeed.

    Prefers passwordless sudo paths used by appliance sudoers; bare loginctl /
    systemctl often fail without polkit and are last resorts.
    """
    attempts: List[Sequence[str]] = [
        ("sudo", "-n", "/usr/sbin/poweroff"),
        ("sudo", "-n", "/sbin/poweroff"),
        ("sudo", "-n", "/usr/bin/systemctl", "poweroff"),
        ("sudo", "-n", "/bin/systemctl", "poweroff"),
        ("sudo", "-n", "systemctl", "poweroff"),
        ("loginctl", "poweroff"),
        ("systemctl", "poweroff"),
        ("/usr/sbin/poweroff",),
        ("/sbin/poweroff",),
    ]
    for cmd in attempts:
        try:
            r = subprocess.run(
                list(cmd),
                capture_output=True,
                timeout=5,
                check=False,
            )
            if r.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False
