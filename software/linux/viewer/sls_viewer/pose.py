"""MediaPipe Tasks Pose Landmarker wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

# Landmark index pairs for a simple SLS stick figure (MediaPipe pose topology)
POSE_BONES: Sequence[Tuple[int, int]] = (
    # torso
    (11, 12),
    (11, 23),
    (12, 24),
    (23, 24),
    # left arm
    (11, 13),
    (13, 15),
    # right arm
    (12, 14),
    (14, 16),
    # left leg
    (23, 25),
    (25, 27),
    # right leg
    (24, 26),
    (26, 28),
    # head-ish
    (11, 0),
    (12, 0),
)

# Joints we draw as dots
POSE_JOINTS: Sequence[int] = (
    0,  # nose
    11, 12, 13, 14, 15, 16,
    23, 24, 25, 26, 27, 28,
)


class PoseEstimator:
    def __init__(self, model_path: Path, min_confidence: float = 0.45):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        from mediapipe import Image as MpImage
        from mediapipe import ImageFormat

        if not model_path.is_file():
            raise FileNotFoundError(
                f"Pose model missing: {model_path}. "
                "Download pose_landmarker_lite.task into models/"
            )

        base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=2,
            min_pose_detection_confidence=min_confidence,
            min_pose_presence_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._MpImage = MpImage
        self._ImageFormat = ImageFormat
        self._frame_ts_ms = 0

    def estimate(self, bgr: np.ndarray) -> List[List[Tuple[float, float, float]]]:
        """
        Returns list of poses; each pose is list of (x, y, visibility) in pixel coords
        for landmarks 0..32 (MediaPipe full set; missing as visibility 0).
        """
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._MpImage(image_format=self._ImageFormat.SRGB, data=rgb)
        self._frame_ts_ms += 33
        result = self._landmarker.detect_for_video(mp_image, self._frame_ts_ms)
        h, w = bgr.shape[:2]
        poses: List[List[Tuple[float, float, float]]] = []
        if not result.pose_landmarks:
            return poses
        for pose in result.pose_landmarks:
            pts: List[Tuple[float, float, float]] = []
            for lm in pose:
                pts.append((lm.x * w, lm.y * h, float(getattr(lm, "visibility", 1.0) or 0.0)))
            poses.append(pts)
        return poses

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:
            pass
