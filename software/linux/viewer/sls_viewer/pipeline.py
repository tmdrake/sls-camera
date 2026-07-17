"""Capture → colorize → pose → composite; infinite Kinect reconnect."""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from . import colorize, freenect_io
from .config import Settings
from .pose import PoseEstimator
from .skeleton import draw_skeletons


class FramePipeline:
    def __init__(self, settings: Settings):
        self.s = settings
        self._lock = threading.Lock()
        self._jpeg: Optional[bytes] = None
        self._bgr: Optional[np.ndarray] = None
        self._status = "starting"
        self._fps = 0.0
        self._poses_count = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._kinect: Optional[freenect_io.FreenectSync] = None
        self._pose: Optional[PoseEstimator] = None
        self._frame_i = 0
        self._last_poses = []
        self._reconnect_attempt = 0

    @property
    def status(self) -> str:
        return self._status

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def poses_count(self) -> int:
        return self._poses_count

    @property
    def mirror(self) -> bool:
        return self.s.mirror

    @mirror.setter
    def mirror(self, value: bool) -> None:
        self.s.mirror = bool(value)
        self.s.save_persisted()

    @property
    def pose_confidence(self) -> float:
        return float(self.s.pose_min_confidence)

    def set_pose_confidence(self, value: float) -> float:
        self.s.pose_min_confidence = float(value)
        self.s.clamp_pose_confidence()
        self.s.save_persisted()
        if self._pose is not None:
            self._pose.set_min_confidence(self.s.pose_min_confidence)
        return self.s.pose_min_confidence

    def adjust_pose_confidence(self, delta: float) -> float:
        return self.set_pose_confidence(self.pose_confidence + float(delta))

    @property
    def max_poses(self) -> int:
        return int(self.s.max_poses)

    def set_max_poses(self, value: int) -> int:
        self.s.max_poses = int(value)
        self.s.clamp_max_poses()
        self.s.save_persisted()
        if self._pose is not None:
            self._pose.set_max_poses(self.s.max_poses)
        return self.s.max_poses

    def adjust_max_poses(self, delta: int) -> int:
        return self.set_max_poses(self.max_poses + int(delta))

    def reset_pose_defaults(self) -> None:
        self.s.reset_pose_defaults()
        if self._pose is not None:
            self._pose.set_min_confidence(self.s.pose_min_confidence)
            self._pose.set_max_poses(self.s.max_poses)

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg

    def get_bgr(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._bgr is None:
                return None
            return self._bgr.copy()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="sls-pipeline", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        if self._kinect:
            self._kinect.stop()
            self._kinect = None
        if self._pose:
            self._pose.close()
            self._pose = None

    def _set_frame(self, bgr: np.ndarray) -> None:
        ok, buf = cv2.imencode(
            ".jpg",
            bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.s.jpeg_quality],
        )
        with self._lock:
            self._bgr = bgr
            if ok:
                self._jpeg = buf.tobytes()

    def _demo_frames(self) -> Tuple[np.ndarray, np.ndarray]:
        t = time.time()
        yy, xx = np.mgrid[0:480, 0:640]
        depth = (
            1000 + 400 * np.sin(xx / 40.0 + t) + 200 * np.cos(yy / 30.0)
        ).astype(np.uint16)
        depth = np.clip(depth, 1, 2000)
        ir = ((xx + yy + int(t * 30)) % 255).astype(np.uint8)
        cv2.ellipse(ir, (320, 240), (60, 120), 0, 0, 360, 220, -1)
        return depth, ir

    # Backoff between reconnect opens after USB/power loss (seconds)
    RECONNECT_SLEEP_S = 2.0

    def _paint_splash(
        self,
        title: str = "Starting SLS Camera",
        detail: str = "",
        *,
        reconnect: bool = False,
    ) -> None:
        """Simple splash while opening or reconnecting (shown ASAP so UI is not blank)."""
        W, H = self.s.frame_width, self.s.frame_height
        err = np.zeros((H, W, 3), dtype=np.uint8)
        err[:] = (12, 12, 14)
        # Accent bar
        cv2.rectangle(err, (0, 0), (W, 6), (0, 255, 180), -1)

        cv2.putText(
            err,
            "SLS CAMERA",
            (40, 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (0, 255, 180),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            err,
            title,
            (40, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.15,
            (0, 200, 255) if reconnect else (220, 220, 220),
            2,
            cv2.LINE_AA,
        )

        lines = []
        if detail:
            lines.append(detail[:100])
        if reconnect:
            lines.append(
                f"Retry #{self._reconnect_attempt} · every {self.RECONNECT_SLEEP_S:.0f}s"
            )
            lines.append("Check power brick and USB")
        else:
            lines.append("Opening depth sensor…")
            lines.append("Please wait")
        for i, line in enumerate(lines):
            cv2.putText(
                err,
                line,
                (40, 210 + i * 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (160, 160, 160),
                1,
                cv2.LINE_AA,
            )
        self._set_frame(err)

    def _paint_reconnect(self, detail: str = "") -> None:
        self._paint_splash(
            "Reconnecting to SLS Camera",
            detail=detail,
            reconnect=True,
        )

    def _close_kinect(self) -> None:
        if self._kinect:
            try:
                self._kinect.stop()
            except Exception:
                pass
            self._kinect = None

    def _open_kinect(self) -> bool:
        """Open live freenect stream: green LED + auto-level + IR gain 50."""
        # Always tear down previous handle first (USB death leaves bad state)
        self._close_kinect()
        try:
            self._status = "opening SLS camera…"
            self.s.ir_brightness = 50
            self._kinect = freenect_io.FreenectSync(
                index=self.s.device_index,
                video_mode="ir",
                led=freenect_io.LED_GREEN if self.s.led_green else freenect_io.LED_OFF,
                tilt_degs=self.s.tilt_degs,
                auto_level=self.s.auto_level,
                ir_brightness=50,
            )
            self._kinect.prepare()
            depth, ir = self._kinect.get_depth_and_ir()
            self._reconnect_attempt = 0
            self._status = (
                f"live · {depth.shape[1]}x{depth.shape[0]} · LED green · tilt 0°"
            )
            return True
        except Exception as e:
            self._status = f"camera error: {e}"
            self._close_kinect()
            return False

    def _ensure_pose(self) -> None:
        if self._pose is None:
            self._pose = PoseEstimator(
                self.s.model_path,
                min_confidence=self.s.pose_min_confidence,
                max_poses=self.s.max_poses,
                min_joints=self.s.pose_min_joints,
                hold_frames=self.s.pose_hold_frames,
            )

    def _compose(self, depth_bgr: np.ndarray, ir_bgr: np.ndarray) -> np.ndarray:
        W, H = self.s.frame_width, self.s.frame_height
        canvas = cv2.resize(depth_bgr, (W, H), interpolation=cv2.INTER_AREA)

        cv2.putText(
            canvas,
            "DEPTH + SLS",
            (16, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )

        pip_w = max(80, int(self.s.ir_pip_width))
        pip_h = max(60, int(self.s.ir_pip_height))
        margin = max(0, int(self.s.ir_pip_margin))
        pip = cv2.resize(ir_bgr, (pip_w, pip_h), interpolation=cv2.INTER_AREA)
        cv2.putText(
            pip,
            "IR + SLS",
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )

        if self.s.ir_pip_corner == "top-left":
            x0, y0 = margin, margin
        else:
            x0 = W - pip_w - margin
            y0 = margin

        x1, y1 = x0 + pip_w, y0 + pip_h
        cv2.rectangle(canvas, (x0 - 2, y0 - 2), (x1 + 2, y1 + 2), (0, 0, 0), 2)
        cv2.rectangle(canvas, (x0 - 1, y0 - 1), (x1 + 1, y1 + 1), (0, 255, 180), 1)
        canvas[y0:y1, x0:x1] = pip

        cv2.putText(
            canvas,
            f"{self._fps:.1f} FPS  poses:{self._poses_count}",
            (16, H - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )
        return canvas

    def _process_frames(
        self, depth_u16: np.ndarray, ir_u8: np.ndarray, fps_smooth: float
    ) -> float:
        depth_bgr = colorize.colorize_depth(
            depth_u16, self.s.depth_min, self.s.depth_max
        )
        ir_bgr = colorize.ir_to_bgr(ir_u8)

        self._frame_i += 1
        if self._pose and (self._frame_i % max(1, self.s.pose_every_n_frames) == 0):
            try:
                self._last_poses = self._pose.estimate(depth_bgr)[
                    : int(self.s.max_poses)
                ]
            except Exception as e:
                self._status = f"pose: {e}"

        poses = self._last_poses[: self.s.max_poses]
        self._poses_count = len(poses)

        depth_bgr = draw_skeletons(
            depth_bgr,
            poses,
            bone_color=self.s.bone_color,
            joint_color=self.s.joint_color,
            bone_thickness=self.s.bone_thickness,
            joint_radius=self.s.joint_radius,
            min_vis=self.s.skeleton_min_vis,
        )
        ir_bgr = draw_skeletons(
            ir_bgr,
            poses,
            bone_color=self.s.bone_color,
            joint_color=self.s.joint_color,
            bone_thickness=max(1, self.s.bone_thickness),
            joint_radius=max(2, self.s.joint_radius - 1),
            min_vis=self.s.skeleton_min_vis,
        )

        depth_bgr = colorize.maybe_flip(depth_bgr, self.s.mirror)
        ir_bgr = colorize.maybe_flip(ir_bgr, self.s.mirror)
        self._set_frame(self._compose(depth_bgr, ir_bgr))
        return fps_smooth

    def _loop(self) -> None:
        demo = bool(self.s.allow_demo_without_kinect)

        # Splash immediately so startup is not a blank screen
        self._status = "starting…"
        self._paint_splash("Starting SLS Camera", "Loading…")

        # Pose model can load while user sees splash (before freenect open)
        try:
            self._ensure_pose()
            self._paint_splash("Starting SLS Camera", "Opening camera…")
        except Exception as e:
            self._status = f"pose model error: {e}"
            self._paint_splash("Starting SLS Camera", f"pose: {e}")

        use_kinect = self._open_kinect()

        # Infinite reconnect until first success (unless demo)
        while self._running and not use_kinect and not demo:
            self._reconnect_attempt += 1
            self._status = (
                f"reconnecting… attempt {self._reconnect_attempt}"
            )
            self._paint_reconnect(self._status)
            time.sleep(self.RECONNECT_SLEEP_S)
            use_kinect = self._open_kinect()

        if not use_kinect and demo:
            self._status = "demo mode (no camera)"

        fps_smooth = 0.0

        while self._running:
            t0 = time.time()
            try:
                if use_kinect and self._kinect:
                    if self._kinect.is_dead():
                        raise freenect_io.FreenectError(
                            self._kinect.dead_reason() or "USB camera dead"
                        )
                    depth_u16, ir_u8 = self._kinect.get_depth_and_ir()
                else:
                    depth_u16, ir_u8 = self._demo_frames()
                    if not use_kinect:
                        self._status = "demo mode (no kinect)"

                fps_smooth = self._process_frames(depth_u16, ir_u8, fps_smooth)
                dt = time.time() - t0
                inst = 1.0 / dt if dt > 0 else 0.0
                fps_smooth = 0.9 * fps_smooth + 0.1 * inst if fps_smooth else inst
                self._fps = fps_smooth

                min_dt = 1.0 / max(1.0, self.s.target_fps)
                sleep_t = min_dt - (time.time() - t0)
                if sleep_t > 0:
                    time.sleep(sleep_t)

            except freenect_io.FreenectError as e:
                # Device lost / stale frames — full close + infinite reopen
                self._status = f"reconnecting… {e}"
                self._close_kinect()
                use_kinect = False
                self._reconnect_attempt += 1
                self._paint_reconnect(str(e))
                time.sleep(self.RECONNECT_SLEEP_S)
                while self._running and not use_kinect:
                    self._reconnect_attempt += 1
                    self._status = (
                        f"reconnecting… attempt {self._reconnect_attempt}"
                    )
                    self._paint_reconnect(str(e))
                    time.sleep(self.RECONNECT_SLEEP_S)
                    use_kinect = self._open_kinect()
                    if use_kinect:
                        self._status = (
                            "live · reconnected · LED green · tilt 0°"
                        )
            except Exception as e:
                # Treat unexpected freenect/USB failures like a disconnect
                msg = str(e).lower()
                if any(
                    k in msg
                    for k in ("usb", "freenect", "transfer", "libusb", "kinect")
                ):
                    self._status = f"reconnecting… {e}"
                    self._close_kinect()
                    use_kinect = False
                    self._reconnect_attempt += 1
                    self._paint_reconnect(str(e))
                    time.sleep(self.RECONNECT_SLEEP_S)
                    continue
                self._status = f"pipeline: {e}"
                time.sleep(0.25)
