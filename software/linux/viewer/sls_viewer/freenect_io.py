"""ctypes bindings for libfreenect sync API (depth + IR, LED, tilt)."""

from __future__ import annotations

import ctypes
import time
from ctypes import POINTER, c_int, c_uint32, c_void_p, byref
from typing import Optional, Tuple

import numpy as np

# freenect enums (libfreenect.h)
FREENECT_VIDEO_RGB = 0
FREENECT_VIDEO_IR_8BIT = 2
FREENECT_DEPTH_11BIT = 0
FREENECT_DEPTH_MM = 5
FREENECT_DEPTH_REGISTERED = 4

LED_OFF = 0
LED_GREEN = 1
LED_RED = 2
LED_YELLOW = 3
LED_BLINK_GREEN = 4
LED_BLINK_RED_YELLOW = 6

DEPTH_W, DEPTH_H = 640, 480
VIDEO_W, VIDEO_H = 640, 480


class FreenectError(RuntimeError):
    pass


def _load_lib():
    for name in (
        "libfreenect_sync.so.0.5",
        "libfreenect_sync.so.0",
        "libfreenect_sync.so",
    ):
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    raise FreenectError(
        "Could not load libfreenect_sync. Install: sudo apt install libfreenect0.5t64"
    )


class FreenectSync:
    """Grab depth + IR frames; control LED and tilt motor."""

    def __init__(
        self,
        index: int = 0,
        video_mode: str = "ir",
        led: int = LED_GREEN,
        tilt_degs: int = 0,
        auto_level: bool = True,
    ):
        self.index = index
        self.video_mode = video_mode  # "ir" | "rgb"
        self.led = led
        self.tilt_degs = 0 if auto_level else int(tilt_degs)
        self.auto_level = auto_level
        self._lib = _load_lib()
        self._bind()
        self._opened = False
        self._prepared = False

    def _bind(self) -> None:
        lib = self._lib
        lib.freenect_sync_get_depth.argtypes = [
            POINTER(c_void_p),
            POINTER(c_uint32),
            c_int,
            c_int,
        ]
        lib.freenect_sync_get_depth.restype = c_int
        lib.freenect_sync_get_video.argtypes = [
            POINTER(c_void_p),
            POINTER(c_uint32),
            c_int,
            c_int,
        ]
        lib.freenect_sync_get_video.restype = c_int
        lib.freenect_sync_set_led.argtypes = [c_int, c_int]
        lib.freenect_sync_set_led.restype = c_int
        lib.freenect_sync_set_tilt_degs.argtypes = [c_int, c_int]
        lib.freenect_sync_set_tilt_degs.restype = c_int
        lib.freenect_sync_stop.argtypes = []
        lib.freenect_sync_stop.restype = None

    def set_led(self, led: int = LED_GREEN) -> None:
        rc = self._lib.freenect_sync_set_led(int(led), self.index)
        if rc != 0:
            raise FreenectError(f"set_led({led}) failed rc={rc}")
        self.led = led

    def set_tilt_degs(self, degrees: int = 0) -> None:
        """Tilt motor: 0 ≈ level; range typically about -30..+30."""
        deg = int(max(-30, min(30, degrees)))
        rc = self._lib.freenect_sync_set_tilt_degs(deg, self.index)
        if rc != 0:
            raise FreenectError(f"set_tilt_degs({deg}) failed rc={rc}")
        self.tilt_degs = deg

    def prepare(self) -> None:
        """
        Open path: green LED + auto-level tilt (0°), then ready for frames.
        Safe to call once after constructing.
        """
        # Retry a few times — BUSY if a previous process held usbfs
        last_err: Optional[Exception] = None
        for attempt in range(4):
            try:
                # stop any half-open sync state
                try:
                    self._lib.freenect_sync_stop()
                except Exception:
                    pass
                self.set_led(self.led if self.led is not None else LED_GREEN)
                if self.auto_level:
                    self.set_tilt_degs(0)
                else:
                    self.set_tilt_degs(self.tilt_degs)
                # give motor a moment to settle toward level
                time.sleep(0.8 if self.auto_level else 0.2)
                # probe depth to fully claim camera
                _ = self.get_depth_u16()
                self._prepared = True
                self._opened = True
                return
            except FreenectError as e:
                last_err = e
                time.sleep(0.4 * (attempt + 1))
        hints = []
        if gspca_loaded():
            hints.append("gspca_kinect is loaded — try: sudo modprobe -r gspca_kinect")
        hints.append("ensure Kinect power brick is on and USB is free")
        hints.append("kill any stuck freenect/python holding the device")
        raise FreenectError(
            f"Could not open Kinect after retries: {last_err}. " + " | ".join(hints)
        )

    def get_depth_u16(self) -> np.ndarray:
        ptr = c_void_p()
        ts = c_uint32()
        rc = self._lib.freenect_sync_get_depth(
            byref(ptr), byref(ts), self.index, FREENECT_DEPTH_11BIT
        )
        if rc != 0 or not ptr.value:
            raise FreenectError(
                f"freenect_sync_get_depth failed (rc={rc}). "
                "Unload gspca_kinect, check power/USB, run fix-kinect-access.sh"
            )
        buf = ctypes.cast(ptr, POINTER(ctypes.c_uint16 * (DEPTH_W * DEPTH_H))).contents
        arr = np.frombuffer(buf, dtype=np.uint16).reshape(DEPTH_H, DEPTH_W).copy()
        # 11-bit valid range; clamp garbage high bits if present
        arr = np.bitwise_and(arr, 0x7FF)
        self._opened = True
        return arr

    def get_ir_u8(self) -> np.ndarray:
        if self.video_mode != "ir":
            raise FreenectError("video_mode is not ir")
        ptr = c_void_p()
        ts = c_uint32()
        rc = self._lib.freenect_sync_get_video(
            byref(ptr), byref(ts), self.index, FREENECT_VIDEO_IR_8BIT
        )
        if rc != 0 or not ptr.value:
            raise FreenectError(f"freenect_sync_get_video IR failed (rc={rc})")
        buf = ctypes.cast(ptr, POINTER(ctypes.c_uint8 * (VIDEO_W * VIDEO_H))).contents
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(VIDEO_H, VIDEO_W).copy()
        self._opened = True
        return arr

    def get_rgb_u8(self) -> np.ndarray:
        if self.video_mode != "rgb":
            raise FreenectError("video_mode is not rgb")
        ptr = c_void_p()
        ts = c_uint32()
        rc = self._lib.freenect_sync_get_video(
            byref(ptr), byref(ts), self.index, FREENECT_VIDEO_RGB
        )
        if rc != 0 or not ptr.value:
            raise FreenectError(f"freenect_sync_get_video RGB failed (rc={rc})")
        buf = ctypes.cast(ptr, POINTER(ctypes.c_uint8 * (VIDEO_W * VIDEO_H * 3))).contents
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(VIDEO_H, VIDEO_W, 3).copy()
        self._opened = True
        return arr

    def get_depth_and_ir(self) -> Tuple[np.ndarray, np.ndarray]:
        """Depth (uint16) + IR (uint8), 640x480."""
        if not self._prepared:
            self.prepare()
        depth = self.get_depth_u16()
        ir = self.get_ir_u8()
        return depth, ir

    def stop(self) -> None:
        if self._opened or self._prepared:
            try:
                # LED off when releasing the device
                try:
                    self._lib.freenect_sync_set_led(LED_OFF, self.index)
                except Exception:
                    pass
                self._lib.freenect_sync_stop()
            except Exception:
                pass
            self._opened = False
            self._prepared = False

    def __enter__(self):
        self.prepare()
        return self

    def __exit__(self, *args):
        self.stop()


def gspca_loaded() -> bool:
    try:
        with open("/proc/modules", "r", encoding="utf-8") as f:
            return any(line.startswith("gspca_kinect") for line in f)
    except OSError:
        return False
