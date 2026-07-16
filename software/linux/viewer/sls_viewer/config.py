"""Runtime configuration for the SLS viewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VIEWER_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = VIEWER_ROOT / "models" / "pose_landmarker_lite.task"
WEB_ROOT = VIEWER_ROOT / "web"


@dataclass
class Settings:
    # Network (localhost appliance)
    host: str = "127.0.0.1"
    port: int = 8765

    # Kinect index (first device)
    device_index: int = 0

    # Operator stands behind the camera → unmirrored (no selfie flip).
    # Set True only if you want a bathroom-mirror style image.
    mirror: bool = False

    # Pose runs on IR (Kinect cannot stream RGB + IR at once with freenect).
    # IR illuminator lights people well enough for MediaPipe in dark rooms.
    pose_min_confidence: float = 0.45
    pose_every_n_frames: int = 1  # 1 = every frame; raise if CPU-bound

    # Depth colorization (mm-ish raw 11-bit mapped)
    depth_min: int = 500
    depth_max: int = 4500

    # Skeleton look (cyan/green SLS style)
    bone_color: tuple[int, int, int] = (0, 255, 180)  # BGR
    joint_color: tuple[int, int, int] = (0, 255, 255)
    bone_thickness: int = 3
    joint_radius: int = 5

    # Composite layout (pixels of streamed frame)
    frame_width: int = 1280
    frame_height: int = 720
    ir_panel_width: int = 360

    jpeg_quality: int = 80
    target_fps: float = 20.0

    model_path: Path = field(default_factory=lambda: MODEL_PATH)

    # If freenect fails, optional demo pattern so UI can still be tested
    allow_demo_without_kinect: bool = False


settings = Settings()
