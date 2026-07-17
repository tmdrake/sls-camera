"""libfreenect device capture: depth + IR, LED, tilt, IR sensor brightness."""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_double,
    c_int,
    c_int8,
    c_int16,
    c_int32,
    c_uint16,
    c_uint32,
    c_void_p,
)
from typing import Optional, Tuple

import numpy as np

# Enums from libfreenect.h
FREENECT_RESOLUTION_MEDIUM = 1
FREENECT_VIDEO_IR_8BIT = 2
FREENECT_VIDEO_RGB = 0
FREENECT_DEPTH_11BIT = 0

LED_OFF = 0
LED_GREEN = 1

# IR sensor gain only (not projector power). freenect range 1–50.
# App uses full gain 50 (no Settings UI); affects IR PiP display only.
IR_BRIGHTNESS_DEFAULT = 50
IR_BRIGHTNESS_MIN = 1
IR_BRIGHTNESS_MAX = 50

DEPTH_W, DEPTH_H = 640, 480
# IR medium is 640x488 in freenect; we crop to 640x480 to match depth.
IR_W, IR_H_NATIVE = 640, 488

# Frame / reconnect timing (seconds)
# If no new depth/video callback arrives within STALE_FRAME_S, treat device as dead
# (USB unplug / power brick loss leaves last frame in memory otherwise).
STALE_FRAME_S = 1.5
# Wait this long for a fresh frame on each get_* call
FRAME_WAIT_S = 2.0
# First open after prepare(): wait for both streams (return as soon as frames arrive)
OPEN_FRAME_WAIT_S = 4.0
# How many freenect_process_events failures before marking dead
EVENT_FAIL_LIMIT = 8
# Internal open attempts per prepare() — keep short so startup fails fast to splash retry
PREPARE_ATTEMPTS = 3


class FreenectError(RuntimeError):
    pass


class _Ctx(Structure):
    pass


class _Dev(Structure):
    pass


class _FrameMode(Structure):
    _fields_ = [
        ("reserved", c_uint32),
        ("resolution", c_int32),
        ("fmt", c_int32),
        ("bytes", c_int32),
        ("width", c_int16),
        ("height", c_int16),
        ("data_bits_per_pixel", c_int8),
        ("padding_bits_per_pixel", c_int8),
        ("framerate", c_int8),
        ("is_valid", c_int8),
    ]


_DEPTH_CB = CFUNCTYPE(None, POINTER(_Dev), c_void_p, c_uint32)
_VIDEO_CB = CFUNCTYPE(None, POINTER(_Dev), c_void_p, c_uint32)


def _load_lib():
    for name in ("libfreenect.so.0.5", "libfreenect.so.0", "libfreenect.so"):
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    raise FreenectError("Could not load libfreenect. Install libfreenect0.5t64")


class FreenectSync:
    """
    Live Kinect capture (depth + IR).

    Named FreenectSync for compatibility with pipeline imports; implemented with
    the async device API so we can set IR sensor brightness, LED, and tilt.
    """

    def __init__(
        self,
        index: int = 0,
        video_mode: str = "ir",
        led: int = LED_GREEN,
        tilt_degs: int = 0,
        auto_level: bool = True,
        ir_brightness: int = IR_BRIGHTNESS_DEFAULT,
    ):
        self.index = index
        self.video_mode = video_mode  # "ir" | "rgb"
        self.led = led
        self.tilt_degs = 0 if auto_level else int(tilt_degs)
        self.auto_level = auto_level
        self.ir_brightness = int(
            max(IR_BRIGHTNESS_MIN, min(IR_BRIGHTNESS_MAX, ir_brightness))
        )
        self._lib = _load_lib()
        self._bind()
        self._ctx = None
        self._dev = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._depth: Optional[np.ndarray] = None
        self._video: Optional[np.ndarray] = None
        self._prepared = False
        self._last_depth_ts = 0.0
        self._last_video_ts = 0.0
        self._dead = False
        self._dead_reason = ""
        self._event_fails = 0
        # Keep callback refs alive
        self._depth_cb = _DEPTH_CB(self._on_depth)
        self._video_cb = _VIDEO_CB(self._on_video)

    def _bind(self) -> None:
        lib = self._lib
        lib.freenect_init.argtypes = [POINTER(POINTER(_Ctx)), c_void_p]
        lib.freenect_init.restype = c_int
        lib.freenect_shutdown.argtypes = [POINTER(_Ctx)]
        lib.freenect_shutdown.restype = c_int
        lib.freenect_num_devices.argtypes = [POINTER(_Ctx)]
        lib.freenect_num_devices.restype = c_int
        lib.freenect_open_device.argtypes = [
            POINTER(_Ctx),
            POINTER(POINTER(_Dev)),
            c_int,
        ]
        lib.freenect_open_device.restype = c_int
        lib.freenect_close_device.argtypes = [POINTER(_Dev)]
        lib.freenect_close_device.restype = c_int
        lib.freenect_find_depth_mode.argtypes = [c_int, c_int]
        lib.freenect_find_depth_mode.restype = _FrameMode
        lib.freenect_find_video_mode.argtypes = [c_int, c_int]
        lib.freenect_find_video_mode.restype = _FrameMode
        lib.freenect_set_depth_mode.argtypes = [POINTER(_Dev), _FrameMode]
        lib.freenect_set_depth_mode.restype = c_int
        lib.freenect_set_video_mode.argtypes = [POINTER(_Dev), _FrameMode]
        lib.freenect_set_video_mode.restype = c_int
        lib.freenect_set_depth_callback.argtypes = [POINTER(_Dev), _DEPTH_CB]
        lib.freenect_set_video_callback.argtypes = [POINTER(_Dev), _VIDEO_CB]
        lib.freenect_start_depth.argtypes = [POINTER(_Dev)]
        lib.freenect_start_depth.restype = c_int
        lib.freenect_start_video.argtypes = [POINTER(_Dev)]
        lib.freenect_start_video.restype = c_int
        lib.freenect_stop_depth.argtypes = [POINTER(_Dev)]
        lib.freenect_stop_video.argtypes = [POINTER(_Dev)]
        lib.freenect_process_events.argtypes = [POINTER(_Ctx)]
        lib.freenect_process_events.restype = c_int
        lib.freenect_set_led.argtypes = [POINTER(_Dev), c_int]
        lib.freenect_set_led.restype = c_int
        lib.freenect_set_tilt_degs.argtypes = [POINTER(_Dev), c_double]
        lib.freenect_set_tilt_degs.restype = c_int
        lib.freenect_set_ir_brightness.argtypes = [POINTER(_Dev), c_uint16]
        lib.freenect_set_ir_brightness.restype = c_int
        lib.freenect_get_ir_brightness.argtypes = [POINTER(_Dev)]
        lib.freenect_get_ir_brightness.restype = c_int

    def _mark_dead(self, reason: str) -> None:
        with self._lock:
            self._dead = True
            self._dead_reason = reason or "device dead"

    def is_dead(self) -> bool:
        with self._lock:
            return bool(self._dead)

    def dead_reason(self) -> str:
        with self._lock:
            return self._dead_reason or ""

    def _on_depth(self, dev, data, ts) -> None:
        n = DEPTH_W * DEPTH_H
        arr = np.ctypeslib.as_array(
            ctypes.cast(data, POINTER(c_uint16 * n)).contents
        ).reshape(DEPTH_H, DEPTH_W)
        frame = np.bitwise_and(arr, 0x7FF).copy()
        now = time.time()
        with self._lock:
            self._depth = frame
            self._last_depth_ts = now
            self._event_fails = 0

    def _on_video(self, dev, data, ts) -> None:
        if self.video_mode == "ir":
            # 640x488 IR_8BIT
            n = IR_W * IR_H_NATIVE
            arr = np.ctypeslib.as_array(
                ctypes.cast(data, POINTER(ctypes.c_uint8 * n)).contents
            ).reshape(IR_H_NATIVE, IR_W)
            # Crop to 640x480 (drop bottom 8 lines) to align with depth
            frame = arr[:DEPTH_H, :].copy()
        else:
            n = DEPTH_W * DEPTH_H * 3
            arr = np.ctypeslib.as_array(
                ctypes.cast(data, POINTER(ctypes.c_uint8 * n)).contents
            ).reshape(DEPTH_H, DEPTH_W, 3)
            frame = arr.copy()
        now = time.time()
        with self._lock:
            self._video = frame
            self._last_video_ts = now
            self._event_fails = 0

    def _event_loop(self) -> None:
        while self._running and self._ctx:
            try:
                rc = int(self._lib.freenect_process_events(self._ctx))
            except Exception:
                self._mark_dead("freenect_process_events exception")
                break
            if rc < 0:
                # libusb / device errors (unplug, transfer -4, etc.)
                with self._lock:
                    self._event_fails += 1
                    fails = self._event_fails
                if fails >= EVENT_FAIL_LIMIT:
                    self._mark_dead(f"freenect_process_events rc={rc}")
                    break
                time.sleep(0.02)
            else:
                with self._lock:
                    self._event_fails = 0

    def prepare(self) -> None:
        if self._prepared and not self.is_dead():
            return
        # Always full stop before (re)open — required after USB death
        self.stop()
        last_err: Optional[Exception] = None
        for attempt in range(PREPARE_ATTEMPTS):
            try:
                self._open_once()
                return
            except FreenectError as e:
                last_err = e
                self.stop()
                # Brief pause; pipeline does longer backoff between full prepares
                if attempt + 1 < PREPARE_ATTEMPTS:
                    time.sleep(0.35 * (attempt + 1))
        hints = []
        if gspca_loaded():
            hints.append("sudo modprobe -r gspca_kinect")
        hints.append("power brick on; free USB; no other freenect app")
        raise FreenectError(
            f"Could not open camera: {last_err}. " + " | ".join(hints)
        )

    def _open_once(self) -> None:
        lib = self._lib
        self._dead = False
        self._dead_reason = ""
        self._event_fails = 0
        self._last_depth_ts = 0.0
        self._last_video_ts = 0.0
        with self._lock:
            self._depth = None
            self._video = None

        ctx = POINTER(_Ctx)()
        if lib.freenect_init(byref(ctx), None) != 0:
            raise FreenectError("freenect_init failed")
        self._ctx = ctx
        n = lib.freenect_num_devices(ctx)
        if n < 1:
            raise FreenectError("No Kinect devices found")
        dev = POINTER(_Dev)()
        if lib.freenect_open_device(ctx, byref(dev), self.index) != 0:
            raise FreenectError("freenect_open_device failed (BUSY?)")
        self._dev = dev

        # LED green
        lib.freenect_set_led(dev, self.led if self.led is not None else LED_GREEN)
        # Auto-level
        if self.auto_level:
            lib.freenect_set_tilt_degs(dev, 0.0)
        else:
            lib.freenect_set_tilt_degs(dev, float(self.tilt_degs))

        # IR sensor brightness (1–50). Does not change IR projector power.
        if self.video_mode == "ir":
            lib.freenect_set_ir_brightness(dev, c_uint16(self.ir_brightness))

        dm = lib.freenect_find_depth_mode(
            FREENECT_RESOLUTION_MEDIUM, FREENECT_DEPTH_11BIT
        )
        if not dm.is_valid:
            raise FreenectError("invalid depth mode")
        vfmt = (
            FREENECT_VIDEO_IR_8BIT
            if self.video_mode == "ir"
            else FREENECT_VIDEO_RGB
        )
        vm = lib.freenect_find_video_mode(FREENECT_RESOLUTION_MEDIUM, vfmt)
        if not vm.is_valid:
            raise FreenectError("invalid video mode")
        if lib.freenect_set_depth_mode(dev, dm) != 0:
            raise FreenectError("set_depth_mode failed")
        if lib.freenect_set_video_mode(dev, vm) != 0:
            raise FreenectError("set_video_mode failed")

        lib.freenect_set_depth_callback(dev, self._depth_cb)
        lib.freenect_set_video_callback(dev, self._video_cb)
        if lib.freenect_start_depth(dev) != 0:
            raise FreenectError("start_depth failed")
        if lib.freenect_start_video(dev) != 0:
            raise FreenectError("start_video failed")

        self._running = True
        self._thread = threading.Thread(
            target=self._event_loop, name="freenect-events", daemon=True
        )
        self._thread.start()

        # Wait for first frames (USB reattach can be slow)
        deadline = time.time() + OPEN_FRAME_WAIT_S
        while time.time() < deadline:
            if self.is_dead():
                raise FreenectError(
                    f"device died during open: {self.dead_reason()}"
                )
            with self._lock:
                ok = (
                    self._depth is not None
                    and self._video is not None
                    and self._last_depth_ts > 0
                    and self._last_video_ts > 0
                )
            if ok:
                self._prepared = True
                return
            time.sleep(0.05)
        raise FreenectError("timeout waiting for depth/video frames")

    def get_ir_brightness(self) -> int:
        if not self._dev or self.is_dead():
            return -1
        return int(self._lib.freenect_get_ir_brightness(self._dev))

    def set_ir_brightness(self, value: int) -> None:
        value = int(max(IR_BRIGHTNESS_MIN, min(IR_BRIGHTNESS_MAX, value)))
        if not self._dev or self.is_dead():
            raise FreenectError("device not open")
        if self._lib.freenect_set_ir_brightness(self._dev, c_uint16(value)) != 0:
            raise FreenectError("set_ir_brightness failed")
        self.ir_brightness = value

    def _wait_fresh_frame(
        self, which: str, wait_s: float = FRAME_WAIT_S
    ) -> np.ndarray:
        """Return a recent frame or raise FreenectError (triggers pipeline reconnect)."""
        if not self._prepared or self.is_dead():
            reason = self.dead_reason() or "not prepared"
            raise FreenectError(f"device unavailable: {reason}")

        deadline = time.time() + float(wait_s)
        while time.time() < deadline:
            if self.is_dead():
                raise FreenectError(
                    f"USB camera dead: {self.dead_reason() or 'transfer failed'}"
                )
            now = time.time()
            with self._lock:
                if which == "depth":
                    frame = self._depth
                    ts = self._last_depth_ts
                else:
                    frame = self._video
                    ts = self._last_video_ts
                if frame is not None and ts > 0 and (now - ts) <= STALE_FRAME_S:
                    return frame.copy()
            time.sleep(0.01)

        # Stale = same symptom as "USB camera marked dead" without a raise
        age = 0.0
        with self._lock:
            ts = self._last_depth_ts if which == "depth" else self._last_video_ts
            if ts > 0:
                age = time.time() - ts
        self._mark_dead(f"stale {which} frame age={age:.1f}s")
        raise FreenectError(
            f"no fresh {which} frame (stale {age:.1f}s — USB/power lost?)"
        )

    def get_depth_u16(self) -> np.ndarray:
        if not self._prepared:
            self.prepare()
        return self._wait_fresh_frame("depth")

    def get_ir_u8(self) -> np.ndarray:
        if self.video_mode != "ir":
            raise FreenectError("video_mode is not ir")
        if not self._prepared:
            self.prepare()
        return self._wait_fresh_frame("video")

    def get_rgb_u8(self) -> np.ndarray:
        if self.video_mode != "rgb":
            raise FreenectError("video_mode is not rgb")
        if not self._prepared:
            self.prepare()
        return self._wait_fresh_frame("video")

    def get_depth_and_ir(self) -> Tuple[np.ndarray, np.ndarray]:
        """Raises FreenectError on USB death / stale frames so pipeline can reconnect."""
        if self.is_dead():
            raise FreenectError(
                f"USB camera dead: {self.dead_reason() or 'transfer failed'}"
            )
        if not self._prepared:
            self.prepare()
        depth = self._wait_fresh_frame("depth")
        ir = self._wait_fresh_frame("video")
        return depth, ir

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        lib = self._lib
        if self._dev:
            try:
                lib.freenect_stop_video(self._dev)
            except Exception:
                pass
            try:
                lib.freenect_stop_depth(self._dev)
            except Exception:
                pass
            try:
                lib.freenect_set_led(self._dev, LED_OFF)
            except Exception:
                pass
            try:
                lib.freenect_close_device(self._dev)
            except Exception:
                pass
            self._dev = None
        if self._ctx:
            try:
                lib.freenect_shutdown(self._ctx)
            except Exception:
                pass
            self._ctx = None
        self._prepared = False
        self._dead = False
        self._dead_reason = ""
        self._event_fails = 0
        with self._lock:
            self._depth = None
            self._video = None
            self._last_depth_ts = 0.0
            self._last_video_ts = 0.0

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
