"""Keep the display awake while the SLS field UI runs (issue #9).

Layers (best-effort; each may fail silently on some hosts):

1. Session D-Bus ``org.freedesktop.ScreenSaver.Inhibit`` (GNOME/KDE/etc.)
2. ``systemd-inhibit --what=idle:sleep`` long-lived child process
3. X11 ``xset s off`` / ``xset -dpms`` fallback (+ light refresh timer)

Release everything on stop / process exit.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, List, Optional

log = logging.getLogger(__name__)

_WHO = "sls-camera"
_WHY = "SLS field investigation UI"


@dataclass
class DisplayInhibit:
    """Hold screensaver / idle / DPMS inhibits for the field session."""

    active: bool = False
    detail: str = ""
    _ss_cookie: Optional[int] = None
    _ss_iface: Any = None
    _inhibit_proc: Optional[subprocess.Popen] = None
    _layers: List[str] = field(default_factory=list)
    _atexit_registered: bool = False

    def start(self) -> bool:
        """Acquire inhibits. Safe to call when already active."""
        if self.active:
            return True
        self._layers = []
        self._ss_cookie = None
        self._ss_iface = None
        self._inhibit_proc = None

        if self._inhibit_screensaver_dbus():
            self._layers.append("screensaver-dbus")
        if self._inhibit_idle_sleep():
            self._layers.append("systemd-inhibit")
        if self._xset_disable_blank():
            self._layers.append("xset")

        self.active = bool(self._layers)
        self.detail = "+".join(self._layers) if self._layers else "none"
        if self.active and not self._atexit_registered:
            atexit.register(self.stop)
            self._atexit_registered = True
        if self.active:
            log.info("display inhibit on: %s", self.detail)
        else:
            log.warning("display inhibit: no method succeeded")
        return self.active

    def stop(self) -> None:
        """Release all inhibits."""
        if self._ss_cookie is not None and self._ss_iface is not None:
            try:
                self._ss_iface.call("UnInhibit", self._ss_cookie)
            except Exception as exc:
                log.debug("UnInhibit failed: %s", exc)
            self._ss_cookie = None
            self._ss_iface = None

        if self._inhibit_proc is not None:
            try:
                self._inhibit_proc.terminate()
                self._inhibit_proc.wait(timeout=2)
            except Exception:
                try:
                    self._inhibit_proc.kill()
                except Exception:
                    pass
            self._inhibit_proc = None

        # Leave DPMS as-is on stop (session defaults / firmware own idle policy)
        was = self.active
        self.active = False
        self.detail = ""
        self._layers = []
        if was:
            log.info("display inhibit off")

    def refresh_x11(self) -> None:
        """Re-assert xset flags (some WMs re-enable blanking)."""
        if self.active and "xset" in self._layers:
            self._xset_disable_blank()

    def _inhibit_screensaver_dbus(self) -> bool:
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
        except ImportError:
            return self._inhibit_screensaver_dbus_send()

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return self._inhibit_screensaver_dbus_send()

        # Try standard path first, then GNOME variant
        candidates = (
            ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver",
             "org.freedesktop.ScreenSaver"),
            ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver",
             "org.gnome.ScreenSaver"),
        )
        for service, path, iface_name in candidates:
            try:
                iface = QDBusInterface(service, path, iface_name, bus)
                if not iface.isValid():
                    continue
                reply = iface.call("Inhibit", _WHO, _WHY)
                if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                    continue
                args = reply.arguments()
                if not args:
                    continue
                cookie = int(args[0])
                self._ss_cookie = cookie
                self._ss_iface = iface
                return True
            except Exception as exc:
                log.debug("screensaver dbus %s: %s", service, exc)
                continue
        return self._inhibit_screensaver_dbus_send()

    def _inhibit_screensaver_dbus_send(self) -> bool:
        if not shutil.which("dbus-send"):
            return False
        try:
            r = subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--dest=org.freedesktop.ScreenSaver",
                    "--type=method_call",
                    "--print-reply",
                    "/org/freedesktop/ScreenSaver",
                    "org.freedesktop.ScreenSaver.Inhibit",
                    f"string:{_WHO}",
                    f"string:{_WHY}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if r.returncode != 0:
                return False
            # Parse "uint32 N" from reply for UnInhibit later if needed
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if "uint32" in line:
                    try:
                        self._ss_cookie = int(line.split()[-1])
                    except ValueError:
                        pass
                    break
            # Without a live iface we cannot UnInhibit via dbus-send easily;
            # cookie alone is enough if we re-call with a helper later.
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _inhibit_idle_sleep(self) -> bool:
        """Hold idle+sleep via a long-lived systemd-inhibit process."""
        if not shutil.which("systemd-inhibit"):
            return False
        try:
            # --mode=block prevents idle sleep while this child runs
            self._inhibit_proc = subprocess.Popen(
                [
                    "systemd-inhibit",
                    f"--what=idle:sleep",
                    f"--who={_WHO}",
                    f"--why={_WHY}",
                    "--mode=block",
                    "sleep",
                    "infinity",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            # Quick check it did not exit immediately
            try:
                rc = self._inhibit_proc.poll()
                if rc is not None:
                    self._inhibit_proc = None
                    return False
            except Exception:
                pass
            return True
        except OSError:
            self._inhibit_proc = None
            return False

    def _xset_disable_blank(self) -> bool:
        if not shutil.which("xset"):
            return False
        display = os.environ.get("DISPLAY")
        if not display:
            return False
        try:
            env = os.environ.copy()
            r1 = subprocess.run(
                ["xset", "s", "off"],
                capture_output=True,
                timeout=3,
                check=False,
                env=env,
            )
            r2 = subprocess.run(
                ["xset", "-dpms"],
                capture_output=True,
                timeout=3,
                check=False,
                env=env,
            )
            r3 = subprocess.run(
                ["xset", "s", "noblank"],
                capture_output=True,
                timeout=3,
                check=False,
                env=env,
            )
            return r1.returncode == 0 or r2.returncode == 0 or r3.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False


# Module singleton for simple use
_default: Optional[DisplayInhibit] = None


def get_display_inhibit() -> DisplayInhibit:
    global _default
    if _default is None:
        _default = DisplayInhibit()
    return _default
