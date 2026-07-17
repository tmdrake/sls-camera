"""Runtime configuration for the SLS viewer (+ simple persistent JSON)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

VIEWER_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = VIEWER_ROOT / "models" / "pose_landmarker_lite.task"
WEB_ROOT = VIEWER_ROOT / "web"
SETTINGS_PATH = VIEWER_ROOT / "user_settings.json"

# Only mirror is user-tweakable for now (IR brightness fixed at 50)
PERSIST_KEYS = ("mirror",)


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    device_index: int = 0

    led_green: bool = True
    auto_level: bool = True
    tilt_degs: int = 0
    # Fixed IR sensor brightness (1–50). No UI control for now.
    ir_brightness: int = 50

    mirror: bool = False

    # Stricter pose to cut false skeletons on colorized depth
    pose_min_confidence: float = 0.55
    pose_every_n_frames: int = 1
    max_poses: int = 2
    # Drop a pose unless this many core joints are confident
    pose_min_joints: int = 6

    depth_min: int = 500
    depth_max: int = 4500

    bone_color: tuple[int, int, int] = (0, 255, 180)
    joint_color: tuple[int, int, int] = (0, 255, 255)
    bone_thickness: int = 3
    joint_radius: int = 5
    skeleton_min_vis: float = 0.45

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
        self.mirror = bool(self.mirror)
        # Always force IR to fixed default (ignore old saved brightness)
        self.ir_brightness = 50

    def save_persisted(self, path: Path = SETTINGS_PATH) -> None:
        data: Dict[str, Any] = {"mirror": bool(self.mirror)}
        try:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass


settings = Settings()
settings.load_persisted()
