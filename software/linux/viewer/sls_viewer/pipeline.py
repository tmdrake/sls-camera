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
        self.s.save_persisted()

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
        """Open live freenect stream: green LED + auto-level tilt, then depth+IR."""
        try:
            self._status = "opening kinect (LED green, auto-level)…"
            # IR brightness fixed at 50 (no UI control)
            self.s.ir_brightness = 50
            self._kinect = freenect_io.FreenectSync(
                index=self.s.device_index,
                video_mode="ir",
                led=freenect_io.LED_GREEN if self.s.led_green else freenect_io.LED_OFF,
                tilt_degs=self.s.tilt_degs,
                auto_level=self.s.auto_level,
                ir_brightness=50,
            )
            self._kinect.prepare()  # LED green + tilt 0° + IR 50 + streams
            depth, ir = self._kinect.get_depth_and_ir()
            self._status = (
                f"live · {depth.shape[1]}x{depth.shape[0]} · "
                f"LED green · tilt 0° · IR 50/50"
            )
            return True
        except Exception as e:
            self._status = f"kinect error: {e}"
            if self._kinect:
                try:
                    self._kinect.stop()
                except Exception:
                    pass
            self._kinect = None
            return False

    def _ensure_pose(self) -> None:
        if self._pose is None:
            self._pose = PoseEstimator(
                self.s.model_path,
                min_confidence=self.s.pose_min_confidence,
                max_poses=self.s.max_poses,
                min_joints=self.s.pose_min_joints,
            )

    def _compose(self, depth_bgr: np.ndarray, ir_bgr: np.ndarray) -> np.ndarray:
        """Full-bleed depth + skeleton; IR + skeleton as small top-corner PiP."""
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

        # IR picture-in-picture (top corner, scaled)
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
            # default top-right
            x0 = W - pip_w - margin
            y0 = margin

        # Border / shadow so PiP reads clearly over depth
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
                    msg[:90],
                    "1) Kinect power brick ON + USB plugged in",
                    "2) sudo modprobe -r gspca_kinect  (if busy)",
                    "3) ./software/linux/scripts/fix-kinect-access.sh",
                    "4) Close other freenect apps; restart this app",
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

                # Pose on colorized depth only (max 2 people). Same FOV as main view.
                self._frame_i += 1
                if self._pose and (self._frame_i % max(1, self.s.pose_every_n_frames) == 0):
                    try:
                        self._last_poses = self._pose.estimate(depth_bgr)[
                            : self.s.max_poses
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
                    bone_thickness=max(2, self.s.bone_thickness - 1),
                    joint_radius=max(3, self.s.joint_radius - 1),
                    min_vis=self.s.skeleton_min_vis,
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
