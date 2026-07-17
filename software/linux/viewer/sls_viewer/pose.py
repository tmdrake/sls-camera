"""MediaPipe Tasks Pose Landmarker — colorized depth, multi-person (1–6)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

POSE_BONES: Sequence[Tuple[int, int]] = (
    (11, 12),
    (11, 23),
    (12, 24),
    (23, 24),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),
    (11, 0),
    (12, 0),
)

POSE_JOINTS: Sequence[int] = (
    0,
    11,
    12,
    13,
    14,
    15,
    16,
    23,
    24,
    25,
    26,
    27,
    28,
)

# Core joints for strength checks
_L_SHOULDER, _R_SHOULDER = 11, 12
_L_HIP, _R_HIP = 23, 24
_CORE_JOINTS = (11, 12, 23, 24, 13, 14, 25, 26)


class PoseEstimator:
    """
    Pose on colorized depth.

    max_poses: simultaneous skeletons (default 4, UI up to 6).
    min_confidence: 0–1; applied to MediaPipe *and* geometry filters.
    """

    def __init__(
        self,
        model_path: Path,
        min_confidence: float = 0.70,
        max_poses: int = 4,
        min_joints: int = 6,
        hold_frames: int = 3,
    ):
        from mediapipe import Image as MpImage
        from mediapipe import ImageFormat
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        if not model_path.is_file():
            raise FileNotFoundError(
                f"Pose model missing: {model_path}. "
                "Download pose_landmarker_lite.task into models/"
            )

        self.model_path = Path(model_path)
        self.max_poses = max(1, int(max_poses))
        self.min_joints = max(1, int(min_joints))
        self.min_confidence = float(min_confidence)
        self.hold_frames = max(1, int(hold_frames))
        self._hold = 0  # consecutive frames with a valid detection
        self._last_good: List[List[Tuple[float, float, float]]] = []

        self._MpImage = MpImage
        self._ImageFormat = ImageFormat
        self._mp_python = mp_python
        self._vision = vision
        self._frame_ts_ms = 0
        self._landmarker = None
        self._build_landmarker()

    def _build_landmarker(self) -> None:
        """Create MediaPipe landmarker using the *actual* UI confidence."""
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
        conf = float(self.min_confidence)
        # MediaPipe expects (0, 1]; clamp
        conf = max(0.05, min(0.99, conf))
        base_options = self._mp_python.BaseOptions(
            model_asset_path=str(self.model_path)
        )
        options = self._vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=self._vision.RunningMode.VIDEO,
            num_poses=self.max_poses,
            min_pose_detection_confidence=conf,
            min_pose_presence_confidence=conf,
            min_tracking_confidence=conf,
        )
        self._landmarker = self._vision.PoseLandmarker.create_from_options(options)
        self._frame_ts_ms = 0  # reset stream clock after rebuild

    def set_min_confidence(self, value: float) -> None:
        """Update confidence and rebuild MediaPipe so the setting actually applies."""
        value = float(max(0.05, min(0.99, value)))
        if abs(value - self.min_confidence) < 0.001:
            return
        self.min_confidence = value
        self._build_landmarker()
        self._hold = 0
        self._last_good = []

    def set_max_poses(self, value: int) -> None:
        """Update simultaneous person cap and rebuild MediaPipe."""
        value = max(1, int(value))
        if value == self.max_poses:
            return
        self.max_poses = value
        self._build_landmarker()
        self._hold = 0
        self._last_good = []

    def _landmark_score(self, lm) -> float:
        vis = float(getattr(lm, "visibility", 0.0) or 0.0)
        pres = float(getattr(lm, "presence", 0.0) or 0.0)
        return max(vis, pres)

    def _geometry_ok(
        self, pts: List[Tuple[float, float, float]], w: int, h: int
    ) -> bool:
        """
        Reject tiny / degenerate sticks. Stricter as confidence rises.
        MediaPipe scores on false-color depth are often inflated, so geometry matters.
        """
        if len(pts) <= max(_R_HIP, _R_SHOULDER):
            return False
        ls, rs = pts[_L_SHOULDER], pts[_R_SHOULDER]
        lh, rh = pts[_L_HIP], pts[_R_HIP]

        # Scale minimum sizes with confidence (0.25 → looser, 0.99 → stricter)
        t = (self.min_confidence - 0.25) / (0.99 - 0.25)
        t = max(0.0, min(1.0, t))
        min_shoulder_frac = 0.04 + 0.08 * t  # 4% → 12% of width
        min_torso_frac = 0.06 + 0.10 * t  # 6% → 16% of height

        shoulder_w = abs(ls[0] - rs[0])
        mid_sx = 0.5 * (ls[0] + rs[0])
        mid_sy = 0.5 * (ls[1] + rs[1])
        mid_hx = 0.5 * (lh[0] + rh[0])
        mid_hy = 0.5 * (lh[1] + rh[1])
        torso_h = mid_hy - mid_sy  # hips below shoulders in image y-down

        if shoulder_w < min_shoulder_frac * w:
            return False
        if torso_h < min_torso_frac * h:
            return False
        # Shoulders should be above hips
        if torso_h <= 0:
            return False
        # Reject absurdly huge full-frame noise blobs
        if shoulder_w > 0.95 * w or torso_h > 0.95 * h:
            return False
        # Torso roughly vertical
        if abs(mid_sx - mid_hx) > 0.35 * w:
            return False
        return True

    def _is_strong_pose(
        self, pts: List[Tuple[float, float, float]], w: int, h: int
    ) -> bool:
        if not self._geometry_ok(pts, w, h):
            return False
        # Score check (when MediaPipe provides real visibility)
        good = 0
        for j in _CORE_JOINTS:
            if j < len(pts) and pts[j][2] >= self.min_confidence * 0.5:
                good += 1
        # At high confidence require more core joints present
        need = self.min_joints
        if self.min_confidence >= 0.75:
            need = max(need, 7)
        if self.min_confidence >= 0.90:
            need = max(need, 8)
        return good >= need

    def estimate(self, bgr: np.ndarray) -> List[List[Tuple[float, float, float]]]:
        if bgr is None or bgr.size == 0:
            return []
        if bgr.ndim == 2:
            bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
        rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        mp_image = self._MpImage(image_format=self._ImageFormat.SRGB, data=rgb)
        self._frame_ts_ms += 33
        result = self._landmarker.detect_for_video(mp_image, self._frame_ts_ms)
        h, w = bgr.shape[:2]
        poses: List[List[Tuple[float, float, float]]] = []
        if result.pose_landmarks:
            for pose in result.pose_landmarks[: self.max_poses]:
                pts: List[Tuple[float, float, float]] = []
                for lm in pose:
                    score = self._landmark_score(lm)
                    pts.append((lm.x * w, lm.y * h, score))
                if self._is_strong_pose(pts, w, h):
                    poses.append(pts)

        # Temporal hold: require consecutive good frames before showing
        # (and hold longer at higher confidence)
        need = self.hold_frames
        if self.min_confidence >= 0.80:
            need = max(need, 4)
        if self.min_confidence >= 0.90:
            need = max(need, 5)

        if poses:
            self._hold += 1
            self._last_good = poses
        else:
            self._hold = 0
            self._last_good = []

        if self._hold >= need:
            return self._last_good
        return []

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None
