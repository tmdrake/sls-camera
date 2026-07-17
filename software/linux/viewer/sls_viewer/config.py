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

    # Hardware defaults on open
    led_green: bool = True  # freenect LED_GREEN while running
    auto_level: bool = True  # tilt motor to 0° (level) on start
    tilt_degs: int = 0  # used only if auto_level is False
    # IR *sensor* brightness 1–50 (not projector). Default 50 = max useful gain.
    # freenect library default is ~30 if unset.
    ir_brightness: int = 50

    # Mirror OFF by default (operator behind camera / unmirrored room view).
    # Use --mirror or UI toggle to turn on.
    mirror: bool = False

    # Pose: MediaPipe is trained on RGB photos. We try colorized depth first
    # (works in dark rooms), then enhanced IR. Lower confidence for IR/depth.
    pose_min_confidence: float = 0.30
    pose_every_n_frames: int = 1  # 1 = every frame; raise if CPU-bound

    # Depth colorization (mm-ish raw 11-bit mapped)
    depth_min: int = 500
    depth_max: int = 4500

    # Skeleton look (cyan/green SLS style)
    bone_color: tuple[int, int, int] = (0, 255, 180)  # BGR
    joint_color: tuple[int, int, int] = (0, 255, 255)
    bone_thickness: int = 3
    joint_radius: int = 5

    # Composite layout: full-bleed depth; IR is a small top-corner PiP
    frame_width: int = 1280
    frame_height: int = 720
    # IR picture-in-picture (top-right by default)
    ir_pip_width: int = 280
    ir_pip_height: int = 210
    ir_pip_margin: int = 12
    ir_pip_corner: str = "top-right"  # top-right | top-left

    jpeg_quality: int = 80
    target_fps: float = 20.0

    model_path: Path = field(default_factory=lambda: MODEL_PATH)

    # If freenect fails, optional demo pattern so UI can still be tested
    allow_demo_without_kinect: bool = False


settings = Settings()
