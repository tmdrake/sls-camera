"""Capture → colorize → pose → composite frame (big depth, small IR)."""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from . import colorize, freenect_io
from .config import Settings
from .pose import PoseEstimator
from .skeleton import draw_skeletons, scale_poses


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

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg

    def get_bgr(self) -> Optional[np.ndarray]:
        """Latest composite BGR frame (copy) for native Qt UI."""
        with self._lock:
            if self._bgr is None:
                return None
            return self._bgr.copy()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="sls-pipeline", daemon=True)
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
        """Synthetic depth/IR for UI testing without Kinect."""
        t = time.time()
        yy, xx = np.mgrid[0:480, 0:640]
        depth = (1000 + 400 * np.sin(xx / 40.0 + t) + 200 * np.cos(yy / 30.0)).astype(np.uint16)
        depth = np.clip(depth, 1, 2000)
        ir = ((xx + yy + int(t * 30)) % 255).astype(np.uint8)
        # fake person blob
        cv2.ellipse(ir, (320, 240), (60, 120), 0, 0, 360, 220, -1)
        return depth, ir

    def _open_kinect(self) -> bool:
        if freenect_io.gspca_loaded():
            self._status = "gspca_kinect loaded — run: sudo modprobe -r gspca_kinect"
            return False
        try:
            self._kinect = freenect_io.FreenectSync(
                index=self.s.device_index, video_mode="ir"
            )
            # Probe one frame
            self._kinect.get_depth_and_ir()
            self._status = "kinect ok"
            return True
        except Exception as e:
            self._status = f"kinect error: {e}"
            if self._kinect:
                self._kinect.stop()
            self._kinect = None
            return False

    def _ensure_pose(self) -> None:
        if self._pose is None:
            self._pose = PoseEstimator(
                self.s.model_path, min_confidence=self.s.pose_min_confidence
            )

    def _compose(self, depth_bgr: np.ndarray, ir_bgr: np.ndarray) -> np.ndarray:
        """Big depth (left) + small IR (right), both with labels."""
        W, H = self.s.frame_width, self.s.frame_height
        ir_w = self.s.ir_panel_width
        main_w = W - ir_w

        main = cv2.resize(depth_bgr, (main_w, H), interpolation=cv2.INTER_AREA)
        side = cv2.resize(ir_bgr, (ir_w, H), interpolation=cv2.INTER_AREA)

        # labels
        cv2.putText(
            main,
            "DEPTH + SLS",
            (16, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            side,
            "IR + SLS",
            (12, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (200, 200, 200),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            side,
            f"{self._fps:.1f} FPS  poses:{self._poses_count}",
            (12, H - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )
        # vertical divider
        canvas = np.zeros((H, W, 3), dtype=np.uint8)
        canvas[:, :main_w] = main
        canvas[:, main_w:] = side
        cv2.line(canvas, (main_w, 0), (main_w, H), (40, 40, 40), 2)
        return canvas

    def _loop(self) -> None:
        use_kinect = self._open_kinect()
        if not use_kinect and not self.s.allow_demo_without_kinect:
            # still paint error frame
            err = np.zeros((self.s.frame_height, self.s.frame_width, 3), dtype=np.uint8)
            msg = self._status[:80]
            cv2.putText(
                err,
                "SLS VIEWER — KINECT NOT OPEN",
                (40, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 80, 255),
                2,
                cv2.LINE_AA,
            )
            for i, line in enumerate(
                [
                    msg,
                    "1) Kinect power brick ON",
                    "2) sudo modprobe -r gspca_kinect",
                    "3) ./software/linux/scripts/fix-kinect-access.sh",
                    "4) restart this app",
                ]
            ):
                cv2.putText(
                    err,
                    line,
                    (40, 200 + i * 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (200, 200, 200),
                    1,
                    cv2.LINE_AA,
                )
            self._set_frame(err)
            # keep refreshing error status occasionally
            while self._running:
                time.sleep(1.0)
                if freenect_io.gspca_loaded() is False and self._open_kinect():
                    use_kinect = True
                    break
                if not self._running:
                    return

        try:
            self._ensure_pose()
        except Exception as e:
            self._status = f"pose model error: {e}"

        t_prev = time.time()
        fps_smooth = 0.0

        while self._running:
            t0 = time.time()
            try:
                if use_kinect and self._kinect:
                    depth_u16, ir_u8 = self._kinect.get_depth_and_ir()
                else:
                    depth_u16, ir_u8 = self._demo_frames()
                    self._status = "demo mode (no kinect)"

                depth_bgr = colorize.colorize_depth(
                    depth_u16, self.s.depth_min, self.s.depth_max
                )
                ir_bgr = colorize.ir_to_bgr(ir_u8)

                # Pose on IR (same 640x480 space as depth for stick alignment)
                self._frame_i += 1
                if self._pose and (self._frame_i % max(1, self.s.pose_every_n_frames) == 0):
                    try:
                        self._last_poses = self._pose.estimate(ir_bgr)
                    except Exception as e:
                        self._status = f"pose: {e}"

                poses = self._last_poses
                self._poses_count = len(poses)

                depth_bgr = draw_skeletons(
                    depth_bgr,
                    poses,
                    bone_color=self.s.bone_color,
                    joint_color=self.s.joint_color,
                    bone_thickness=self.s.bone_thickness,
                    joint_radius=self.s.joint_radius,
                )
                ir_bgr = draw_skeletons(
                    ir_bgr,
                    poses,
                    bone_color=self.s.bone_color,
                    joint_color=self.s.joint_color,
                    bone_thickness=max(2, self.s.bone_thickness - 1),
                    joint_radius=max(3, self.s.joint_radius - 1),
                )

                depth_bgr = colorize.maybe_flip(depth_bgr, self.s.mirror)
                ir_bgr = colorize.maybe_flip(ir_bgr, self.s.mirror)

                composite = self._compose(depth_bgr, ir_bgr)
                self._set_frame(composite)

                dt = time.time() - t0
                inst = 1.0 / dt if dt > 0 else 0.0
                fps_smooth = 0.9 * fps_smooth + 0.1 * inst if fps_smooth else inst
                self._fps = fps_smooth

                # pace
                min_dt = 1.0 / max(1.0, self.s.target_fps)
                sleep_t = min_dt - (time.time() - t0)
                if sleep_t > 0:
                    time.sleep(sleep_t)
            except freenect_io.FreenectError as e:
                self._status = str(e)
                use_kinect = False
                if self._kinect:
                    self._kinect.stop()
                    self._kinect = None
                time.sleep(0.5)
                use_kinect = self._open_kinect()
            except Exception as e:
                self._status = f"pipeline: {e}"
                time.sleep(0.25)
