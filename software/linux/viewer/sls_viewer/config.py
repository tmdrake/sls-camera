"""Runtime configuration for the SLS viewer (+ simple persistent JSON)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict

VIEWER_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = VIEWER_ROOT / "models" / "pose_landmarker_lite.task"
WEB_ROOT = VIEWER_ROOT / "web"
# Persist user tweaks (brightness, mirror) across runs
SETTINGS_PATH = VIEWER_ROOT / "user_settings.json"

# Keys written to user_settings.json
PERSIST_KEYS = ("ir_brightness", "mirror")


@dataclass
class Settings:
    # Network (localhost appliance)
    host: str = "127.0.0.1"
    port: int = 8765

    # Kinect index (first device)
    device_index: int = 0

    # Hardware defaults on open
    led_green: bool = True
    auto_level: bool = True
    tilt_degs: int = 0
    # IR *sensor* brightness 1–50 (not projector). Max useful default 50.
    ir_brightness: int = 50

    # Mirror OFF by default
    mirror: bool = False

    # Pose on colorized depth only; max people drawn/detected
    pose_min_confidence: float = 0.30
    pose_every_n_frames: int = 1
    max_poses: int = 2

    # Depth colorization
    depth_min: int = 500
    depth_max: int = 4500

    # Skeleton look
    bone_color: tuple[int, int, int] = (0, 255, 180)
    joint_color: tuple[int, int, int] = (0, 255, 255)
    bone_thickness: int = 3
    joint_radius: int = 5

    # Layout
    frame_width: int = 1280
    frame_height: int = 720
    ir_pip_width: int = 280
    ir_pip_height: int = 210
    ir_pip_margin: int = 12
    ir_pip_corner: str = "top-right"

    jpeg_quality: int = 80
    target_fps: float = 20.0

    model_path: Path = field(default_factory=lambda: MODEL_PATH)
    allow_demo_without_kinect: bool = False

    def clamp_ir_brightness(self) -> None:
        self.ir_brightness = int(max(1, min(50, int(self.ir_brightness))))

    def load_persisted(self, path: Path = SETTINGS_PATH) -> None:
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        for key in PERSIST_KEYS:
            if key in data:
                setattr(self, key, data[key])
        self.clamp_ir_brightness()
        self.mirror = bool(self.mirror)

    def save_persisted(self, path: Path = SETTINGS_PATH) -> None:
        self.clamp_ir_brightness()
        data: Dict[str, Any] = {
            "ir_brightness": int(self.ir_brightness),
            "mirror": bool(self.mirror),
        }
        try:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass


settings = Settings()
settings.load_persisted()
