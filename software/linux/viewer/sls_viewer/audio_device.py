"""Shared mic device selection (Kinect USB Audio preferred)."""

from __future__ import annotations

from typing import Optional, Tuple

_KINECT_HINTS = (
    "kinect",
    "xbox",
    "nui",
    "microsoft",
    "usb audio",
    "usb-audio",
    "uac",
)


def pick_input_device(sd) -> Tuple[Optional[int], str]:
    """
    Return (device_index or None for default, label).

    Prefers Kinect / USB Audio names after kinect-audio-setup.
    """
    try:
        devices = sd.query_devices()
    except Exception:
        return None, ""

    for i, d in enumerate(devices):
        if int(d.get("max_input_channels", 0) or 0) < 1:
            continue
        name = str(d.get("name", ""))
        low = name.lower()
        if any(h in low for h in _KINECT_HINTS):
            return i, name
    try:
        default = sd.default.device[0]
        name = str(devices[default]["name"]) if default is not None else "default"
        return default, name
    except Exception:
        return None, "default"
