"""MediaPipe Tasks Pose Landmarker wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

import cv2
import numpy as np

# MediaPipe pose topology (lite)
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


class PoseEstimator:
    def __init__(
        self,
        model_path: Path,
        min_confidence: float = 0.35,
        max_poses: int = 2,
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
        base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=self.max_poses,
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
        Returns list of poses; each pose is (x, y, score) in pixel coords.
        """
        if bgr is None or bgr.size == 0:
            return []
        # Ensure 3-channel uint8
        if bgr.ndim == 2:
            bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        # Contiguous for MediaPipe
        rgb = np.ascontiguousarray(rgb)
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
                # Tasks API often fills presence more reliably than visibility
                score = float(
                    getattr(lm, "visibility", 0.0)
                    or getattr(lm, "presence", 0.0)
                    or 0.0
                )
                if score <= 0.0:
                    score = 0.5  # still plot if landmark returned
                pts.append((lm.x * w, lm.y * h, score))
            poses.append(pts)
        return poses

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:
            pass
