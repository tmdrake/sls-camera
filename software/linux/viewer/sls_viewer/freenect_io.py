"""ctypes bindings for libfreenect sync API (depth + IR/RGB)."""

from __future__ import annotations

import ctypes
from ctypes import POINTER, c_int, c_uint32, c_void_p, byref
from typing import Optional, Tuple

import numpy as np

# freenect enums (libfreenect.h)
FREENECT_VIDEO_RGB = 0
FREENECT_VIDEO_IR_8BIT = 2
FREENECT_DEPTH_11BIT = 0
FREENECT_DEPTH_MM = 5
FREENECT_DEPTH_REGISTERED = 4

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
    """Grab depth + IR (or RGB) frames via freenect_sync_*."""

    def __init__(self, index: int = 0, video_mode: str = "ir"):
        self.index = index
        self.video_mode = video_mode  # "ir" | "rgb"
        self._lib = _load_lib()
        self._lib.freenect_sync_get_depth.argtypes = [
            POINTER(c_void_p),
            POINTER(c_uint32),
            c_int,
            c_int,
        ]
        self._lib.freenect_sync_get_depth.restype = c_int
        self._lib.freenect_sync_get_video.argtypes = [
            POINTER(c_void_p),
            POINTER(c_uint32),
            c_int,
            c_int,
        ]
        self._lib.freenect_sync_get_video.restype = c_int
        self._lib.freenect_sync_stop.argtypes = []
        self._lib.freenect_sync_stop.restype = None
        self._opened = False

    @property
    def video_fmt(self) -> int:
        return FREENECT_VIDEO_IR_8BIT if self.video_mode == "ir" else FREENECT_VIDEO_RGB

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
        # Buffer owned by freenect until next call / stop — copy immediately.
        buf = ctypes.cast(ptr, POINTER(ctypes.c_uint16 * (DEPTH_W * DEPTH_H))).contents
        arr = np.frombuffer(buf, dtype=np.uint16).reshape(DEPTH_H, DEPTH_W).copy()
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
        # IR medium is 640x480 for 8-bit
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
        """Depth (uint16) + IR (uint8), same resolution 640x480."""
        depth = self.get_depth_u16()
        ir = self.get_ir_u8()
        return depth, ir

    def stop(self) -> None:
        if self._opened:
            try:
                self._lib.freenect_sync_stop()
            except Exception:
                pass
            self._opened = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()


def gspca_loaded() -> bool:
    try:
        with open("/proc/modules", "r", encoding="utf-8") as f:
            return any(line.startswith("gspca_kinect") for line in f)
    except OSError:
        return False
