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

# Prefer these pure-input labels when no Kinect (built-in / headset mics)
_CAPTURE_HINTS = (
    "headset",
    "internal mic",
    "internal",
    "microphone",
    "mic",
    "capture",
    "input",
)


def _channels(d: dict, key: str) -> int:
    try:
        return int(d.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def pick_input_device(sd) -> Tuple[Optional[int], str]:
    """
    Return (device_index or None for default, label).

    Prefers Kinect / USB Audio names after kinect-audio-setup.

    RCA / PipeWire note (lab 2026-07-24): opening PortAudio on duplex
    ``default`` / ``pipewire`` creates a *playback* node stuck in ``[init]``
    alongside capture. That holds Built-in Headphones busy → DrakeVox only
    a click/pop then silence. Prefer **capture-only** devices
    (max_output_channels == 0) when no Kinect is present.
    """
    try:
        devices = sd.query_devices()
    except Exception:
        return None, ""

    # 1) Kinect / USB array (may be multi-channel capture)
    for i, d in enumerate(devices):
        if _channels(d, "max_input_channels") < 1:
            continue
        name = str(d.get("name", ""))
        low = name.lower()
        if any(h in low for h in _KINECT_HINTS):
            return i, name

    # 2) Capture-only PortAudio devices (no output channels)
    pure: list[Tuple[int, str]] = []
    for i, d in enumerate(devices):
        if _channels(d, "max_input_channels") < 1:
            continue
        if _channels(d, "max_output_channels") > 0:
            continue
        name = str(d.get("name", ""))
        low = name.lower()
        if "monitor" in low:
            continue
        pure.append((i, name))

    if pure:
        for i, name in pure:
            low = name.lower()
            if any(h in low for h in _CAPTURE_HINTS):
                return i, name
        return pure[0]

    # 3) Fall back to default *input* index (may still be duplex — last resort)
    try:
        default = sd.default.device[0]
        if default is not None:
            idx = int(default)
            name = str(devices[idx]["name"]) if 0 <= idx < len(devices) else "default"
            return idx, name
    except Exception:
        pass
    return None, "default"
