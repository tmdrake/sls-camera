"""Parent-side freenect client: frames from isolated worker process (#16).

If libfreenect SIGSEGVs on USB unplug, only the worker dies; the Qt app stays
up and the pipeline reconnect path restarts a new worker.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from .freenect_io import (
    DEPTH_H,
    DEPTH_W,
    FRAME_WAIT_S,
    FreenectError,
    IR_BRIGHTNESS_DEFAULT,
    IR_BRIGHTNESS_MAX,
    IR_BRIGHTNESS_MIN,
    LED_GREEN,
    LED_OFF,
    OPEN_FRAME_WAIT_S,
    STALE_FRAME_S,
)

MAGIC = b"SLFK"
TYPE_FRAME = 1
TYPE_OK = 2
TYPE_ERR = 3
TYPE_DEAD = 4
TYPE_PONG = 5

_HDR = struct.Struct("!4sBI")
DEPTH_BYTES = DEPTH_W * DEPTH_H * 2
IR_BYTES = DEPTH_W * DEPTH_H


def freenect_isolate_enabled() -> bool:
    """Default ON. Set SLS_FREENECT_ISOLATE=0 to use in-process freenect."""
    raw = (os.environ.get("SLS_FREENECT_ISOLATE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "inproc", "native")


class FreenectProxy:
    """Same surface as FreenectNative: prepare / get_depth_and_ir / set_led / stop."""

    def __init__(
        self,
        index: int = 0,
        video_mode: str = "ir",
        led: int = LED_GREEN,
        tilt_degs: int = 0,
        auto_level: bool = True,
        ir_brightness: int = IR_BRIGHTNESS_DEFAULT,
    ):
        self.index = int(index)
        self.video_mode = "ir"
        self.led = int(led if led is not None else LED_GREEN)
        self.tilt_degs = 0 if auto_level else int(tilt_degs)
        self.auto_level = bool(auto_level)
        self.ir_brightness = int(
            max(IR_BRIGHTNESS_MIN, min(IR_BRIGHTNESS_MAX, ir_brightness))
        )
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._depth: Optional[np.ndarray] = None
        self._video: Optional[np.ndarray] = None
        self._last_depth_ts = 0.0
        self._last_video_ts = 0.0
        self._prepared = False
        self._dead = False
        self._dead_reason = ""
        self._running = False
        self._last_err = ""

    def is_dead(self) -> bool:
        with self._lock:
            if self._dead:
                return True
        if self._proc is not None and self._proc.poll() is not None:
            self._mark_dead(
                f"worker exited code={self._proc.returncode} "
                f"(likely libfreenect fault on USB unplug)"
            )
            return True
        return False

    def dead_reason(self) -> str:
        with self._lock:
            return self._dead_reason or ""

    def _mark_dead(self, reason: str) -> None:
        with self._lock:
            self._dead = True
            self._dead_reason = reason or "device dead"

    def _cmd(self, obj: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise FreenectError("worker not running")
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()
        except BrokenPipeError as e:
            self._mark_dead(f"worker pipe broken: {e}")
            raise FreenectError(self.dead_reason()) from e

    def _spawn(self) -> None:
        self.stop()
        # Ensure package root is on path for -m sls_viewer.freenect_worker
        env = os.environ.copy()
        # Worker must not inherit isolate recursion
        env["SLS_FREENECT_ISOLATE"] = "0"
        cmd = [sys.executable, "-m", "sls_viewer.freenect_worker"]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            bufsize=0,
        )
        self._running = True
        self._dead = False
        self._dead_reason = ""
        self._reader = threading.Thread(
            target=self._read_loop, name="freenect-proxy-rd", daemon=True
        )
        self._reader.start()
        # Drain stderr so worker never blocks on full pipe
        threading.Thread(
            target=self._drain_stderr, name="freenect-proxy-err", daemon=True
        ).start()

    def _drain_stderr(self) -> None:
        p = self._proc
        if p is None or p.stderr is None:
            return
        try:
            for line in iter(p.stderr.readline, b""):
                if not line:
                    break
                # Keep for debug; avoid flooding — last line only in dead reason
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    with self._lock:
                        self._last_err = text[-200:]
        except Exception:
            pass

    def _read_loop(self) -> None:
        p = self._proc
        if p is None or p.stdout is None:
            return
        buf = p.stdout
        try:
            while self._running and p.poll() is None:
                hdr = buf.read(_HDR.size)
                if not hdr or len(hdr) < _HDR.size:
                    break
                magic, mtype, plen = _HDR.unpack(hdr)
                if magic != MAGIC:
                    self._mark_dead("bad worker magic (protocol error)")
                    break
                payload = buf.read(int(plen)) if plen else b""
                if plen and len(payload) < plen:
                    self._mark_dead("worker short read")
                    break
                if mtype == TYPE_FRAME:
                    if len(payload) < DEPTH_BYTES + IR_BYTES:
                        continue
                    d = np.frombuffer(payload[:DEPTH_BYTES], dtype=np.uint16).reshape(
                        DEPTH_H, DEPTH_W
                    ).copy()
                    ir = np.frombuffer(
                        payload[DEPTH_BYTES : DEPTH_BYTES + IR_BYTES], dtype=np.uint8
                    ).reshape(DEPTH_H, DEPTH_W).copy()
                    now = time.time()
                    with self._lock:
                        self._depth = d
                        self._video = ir
                        self._last_depth_ts = now
                        self._last_video_ts = now
                elif mtype == TYPE_DEAD:
                    reason = payload.decode("utf-8", errors="replace") or "worker dead"
                    self._mark_dead(reason)
                    break
                elif mtype == TYPE_ERR:
                    msg = payload.decode("utf-8", errors="replace")
                    with self._lock:
                        self._last_err = msg
                elif mtype in (TYPE_OK, TYPE_PONG):
                    pass
        except Exception as e:
            self._mark_dead(f"proxy read: {e}")
        finally:
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                code = proc.returncode
                with self._lock:
                    already = self._dead
                    reason = self._dead_reason or ""
                if not already:
                    # 139 / -11 = SIGSEGV typical on hard unplug in libfreenect
                    tag = ""
                    if code in (-11, 139) or (isinstance(code, int) and code == 139):
                        tag = " (SIGSEGV/libfreenect?)"
                    self._mark_dead(f"worker exited code={code}{tag}")
                elif "worker exited" not in reason and code is not None:
                    pass

    def _wait_msg_err_or_ok(self, timeout: float = 8.0) -> None:
        """After open/close command, wait until frames appear or dead/err."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_dead():
                raise FreenectError(self.dead_reason() or "worker dead")
            with self._lock:
                err = self._last_err
                ready = (
                    self._depth is not None
                    and self._video is not None
                    and self._last_depth_ts > 0
                )
            if ready:
                return
            # open failed with ERR (no frames)
            if err and "Could not open" in err or (err and "open" in err.lower()):
                # only treat as failure if still no frames after short wait
                pass
            if err and not ready and time.time() + 0.3 > deadline:
                raise FreenectError(err)
            time.sleep(0.05)
        with self._lock:
            err = self._last_err
        if err:
            raise FreenectError(err)
        raise FreenectError("timeout waiting for worker frames")

    def prepare(self) -> None:
        if self._prepared and not self.is_dead():
            return
        self.stop()
        self._spawn()
        self._cmd(
            {
                "cmd": "open",
                "index": self.index,
                "led": self.led,
                "auto_level": self.auto_level,
                "tilt": self.tilt_degs,
                "ir": self.ir_brightness,
            }
        )
        # Wait for first frame or error
        deadline = time.time() + OPEN_FRAME_WAIT_S + 2.0
        last_err = ""
        while time.time() < deadline:
            if self.is_dead():
                raise FreenectError(self.dead_reason() or "worker died on open")
            with self._lock:
                ready = (
                    self._depth is not None
                    and self._video is not None
                    and self._last_depth_ts > 0
                )
                last_err = self._last_err
            if ready:
                self._prepared = True
                return
            # Explicit open error from worker
            if last_err and any(
                k in last_err.lower()
                for k in ("could not open", "no kinect", "busy", "failed", "timeout")
            ):
                # Give a moment for a race with first frame
                time.sleep(0.2)
                with self._lock:
                    ready = self._depth is not None and self._video is not None
                if not ready:
                    raise FreenectError(last_err)
            time.sleep(0.05)
        raise FreenectError(
            last_err or "timeout waiting for depth/video frames from worker"
        )

    def set_led(self, state: int) -> bool:
        if not self._prepared or self.is_dead():
            return False
        try:
            self._cmd({"cmd": "led", "state": int(state)})
            self.led = int(state)
            return True
        except FreenectError:
            return False

    def get_ir_brightness(self) -> int:
        return int(self.ir_brightness)

    def set_ir_brightness(self, value: int) -> None:
        self.ir_brightness = int(
            max(IR_BRIGHTNESS_MIN, min(IR_BRIGHTNESS_MAX, value))
        )
        # reopen would be needed for worker — rarely used (fixed 50 in app)

    def _wait_fresh_frame(self, which: str, wait_s: float = FRAME_WAIT_S) -> np.ndarray:
        if not self._prepared or self.is_dead():
            raise FreenectError(
                f"device unavailable: {self.dead_reason() or 'not prepared'}"
            )
        deadline = time.time() + float(wait_s)
        while time.time() < deadline:
            if self.is_dead():
                raise FreenectError(
                    f"USB camera dead: {self.dead_reason() or 'worker died'}"
                )
            now = time.time()
            with self._lock:
                if which == "depth":
                    frame, ts = self._depth, self._last_depth_ts
                else:
                    frame, ts = self._video, self._last_video_ts
                if frame is not None and ts > 0 and (now - ts) <= STALE_FRAME_S:
                    return frame.copy()
            time.sleep(0.01)
        age = 0.0
        with self._lock:
            ts = self._last_depth_ts if which == "depth" else self._last_video_ts
            if ts > 0:
                age = time.time() - ts
        self._mark_dead(f"stale {which} frame age={age:.1f}s")
        raise FreenectError(
            f"no fresh {which} frame (stale {age:.1f}s — USB/power lost?)"
        )

    def get_depth_and_ir(self) -> Tuple[np.ndarray, np.ndarray]:
        if self.is_dead():
            raise FreenectError(
                f"USB camera dead: {self.dead_reason() or 'worker died'}"
            )
        if not self._prepared:
            self.prepare()
        depth = self._wait_fresh_frame("depth")
        ir = self._wait_fresh_frame("video")
        return depth, ir

    def stop(self) -> None:
        self._running = False
        self._prepared = False
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                if proc.stdin and proc.poll() is None:
                    proc.stdin.write(b'{"cmd":"stop"}\n')
                    proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._reader is not None and self._reader.is_alive():
            self._reader.join(timeout=1.0)
        self._reader = None
        with self._lock:
            self._depth = None
            self._video = None
            self._last_depth_ts = 0.0
            self._last_video_ts = 0.0
            self._dead = False
            self._dead_reason = ""
            self._last_err = ""

    def __enter__(self):
        self.prepare()
        return self

    def __exit__(self, *args):
        self.stop()
