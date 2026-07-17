"""MediaPipe Tasks Pose Landmarker — colorized depth, max 2 people."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

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

# Core torso/limb joints used to reject weak false positives
_CORE_JOINTS = (11, 12, 23, 24, 13, 14, 25, 26)


class PoseEstimator:
    def __init__(
        self,
        model_path: Path,
        min_confidence: float = 0.55,
        max_poses: int = 2,
        min_joints: int = 6,
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

        self.max_poses = max(1, int(max_poses))
        self.min_joints = max(1, int(min_joints))
        # Runtime filter (UI); MediaPipe uses a lower floor so raising conf is snappy
        self.min_confidence = float(min_confidence)
        detect_floor = min(0.30, self.min_confidence)
        base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=self.max_poses,
            min_pose_detection_confidence=detect_floor,
            min_pose_presence_confidence=detect_floor,
            min_tracking_confidence=detect_floor,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._MpImage = MpImage
        self._ImageFormat = ImageFormat
        self._frame_ts_ms = 0

    def set_min_confidence(self, value: float) -> None:
        """Update live filter threshold (no MediaPipe re-init)."""
        self.min_confidence = float(value)

    def _landmark_score(self, lm) -> float:
        vis = float(getattr(lm, "visibility", 0.0) or 0.0)
        pres = float(getattr(lm, "presence", 0.0) or 0.0)
        return max(vis, pres)

    def _is_strong_pose(
        self, pts: List[Tuple[float, float, float]]
    ) -> bool:
        """Require enough confident core joints (cuts empty-room ghosts)."""
        good = 0
        for j in _CORE_JOINTS:
            if j < len(pts) and pts[j][2] >= self.min_confidence:
                good += 1
        return good >= self.min_joints

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
        if not result.pose_landmarks:
            return poses
        for pose in result.pose_landmarks[: self.max_poses]:
            pts: List[Tuple[float, float, float]] = []
            for lm in pose:
                score = self._landmark_score(lm)
                pts.append((lm.x * w, lm.y * h, score))
            if self._is_strong_pose(pts):
                poses.append(pts)
        return poses

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:
            pass
