"""Runtime configuration for the SLS viewer (+ simple persistent JSON)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .host_power import env_wants_poweroff_on_quit
from .spectrum import DEFAULT_SPECTRUM_STYLE, normalize_spectrum_style

# Atom / 2 GB field tablets (#14) — firmware may export SLS_FIELD_LITE=1
FIELD_LITE_TARGET_FPS = 7.5
FIELD_LITE_RECORD_FPS = 7.5
FIELD_LITE_POSE_EVERY_N = 2

VIEWER_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = VIEWER_ROOT / "models" / "pose_landmarker_lite.task"
WEB_ROOT = VIEWER_ROOT / "web"
SETTINGS_PATH = VIEWER_ROOT / "user_settings.json"

# MediaPipe PoseLandmarker official defaults
# (https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarkerOptions)
# Field default confidence (UI 25%). MediaPipe stock is often 0.5; we start
# looser so depth/SLS sticks appear more readily on tablets.
MEDIAPIPE_DEFAULT_CONFIDENCE = 0.25
MEDIAPIPE_DEFAULT_MAX_POSES = 1

# User-tweakable prefs (IR gain fixed, not UI)
PERSIST_KEYS = (
    "mirror",
    "pose_min_confidence",
    "max_poses",
    "spectrum_enabled",
    "spectrum_style",
    "auto_snap_on_detect",
    "drakevox_enabled",
    "drakevox_on_autosnap",
    "display_brightness",
    "captures_target",
    # quit_powers_off is not persisted (firmware env only)
)


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    device_index: int = 0

    led_green: bool = True
    auto_level: bool = True
    tilt_degs: int = 0
    # IR *sensor* gain only (not projector). freenect range 1–50; full gain = 50.
    # Fixed — no Settings UI. See software/linux/viewer/README.md.
    ir_brightness: int = 50

    mirror: bool = False
    # Field/touch kiosk: hide mouse pointer (CLI --hide-cursor / SLS_HIDE_CURSOR)
    hide_cursor: bool = False

    # Pose confidence (UI-adjustable). Higher = fewer false skeletons.
    # Default 25% (field); range 25–95% in 5% steps. Rebuilds model on change.
    pose_min_confidence: float = MEDIAPIPE_DEFAULT_CONFIDENCE
    pose_conf_min: float = 0.25
    pose_conf_max: float = 0.95  # UI max (0.05 steps: 0.25 … 0.95)
    pose_conf_step: float = 0.05
    pose_every_n_frames: int = 1
    # Simultaneous people (MediaPipe default num_poses=1); UI allows 1–6
    max_poses: int = MEDIAPIPE_DEFAULT_MAX_POSES
    max_poses_min: int = 1
    max_poses_max: int = 6
    pose_min_joints: int = 6
    pose_hold_frames: int = 3

    depth_min: int = 500
    depth_max: int = 4500

    bone_color: tuple[int, int, int] = (0, 255, 180)
    joint_color: tuple[int, int, int] = (0, 255, 255)
    # Thin SLS sticks (was 3 / 5)
    bone_thickness: int = 1
    joint_radius: int = 3
    skeleton_min_vis: float = 0.45

    # Composite / HUD / record canvas (depth sensor is always freenect 640x480)
    frame_width: int = 1280
    frame_height: int = 720
    ir_pip_width: int = 280
    ir_pip_height: int = 210
    ir_pip_margin: int = 12
    ir_pip_corner: str = "top-right"

    jpeg_quality: int = 80
    # Live pipeline sleep cap (see also record_fps). Field Atom: use --field-lite / env.
    target_fps: float = 20.0

    # Spectrum strip (ALSA/Pulse; prefers Kinect UAC after kinect-audio-setup)
    spectrum_enabled: bool = True
    # Visual style id — see spectrum.SPECTRUM_STYLES; default phosphor scope trail
    spectrum_style: str = DEFAULT_SPECTRUM_STYLE
    spectrum_height: int = 56
    spectrum_bars: int = 64  # fixed (no Settings); 48 was default, 64 a bit more detail

    # Session tools
    auto_snap_on_detect: bool = False
    # Match live pipeline target so AVI timing matches what you see on screen
    record_fps: float = 20.0
    # Final container: "avi" (default, field-safe) or "mp4" (opt-in share path #20)
    record_format: str = "avi"
    # Prefer VAAPI H.264 when recording MP4 (still falls back to libx264 / AVI)
    hardware_encode: bool = False
    # Filled at startup by probe: "vaapi" | "libx264" | "none" (empty = not probed yet)
    h264_encoder: str = ""
    # Captures destination: auto = SD/USB if mounted (default); local = viewer/captures only
    captures_target: str = "auto"

    # Performance (#14) — load-time only (not user_settings.json)
    field_lite: bool = False
    # Fast Qt pixmap scale (no SmoothTransformation) — big CPU save on Atom
    display_fast: bool = False
    # Show effective FPS in status bar + denser logs
    show_fps: bool = False
    # Log effective_fps=… every N seconds (0 = off). Never on by default (#14 RCA).
    fps_log_interval_s: float = 0.0

    # DrakeVox (random word every 5–15 min; timestamped + TTS)
    drakevox_enabled: bool = True
    # Fire DrakeVox (word + TTS + burn into JPEG) when auto-snap on detect fires
    drakevox_on_autosnap: bool = True

    # Display brightness 5–100 (None = leave OS default / don't force at start)
    display_brightness: Optional[int] = None

    # Quit power-off *intent* (exit code 10 only). Never from JSON/Settings.
    # True only when firmware sets SLS_QUIT_ACTION=shutdown|poweroff.
    # App does NOT call system poweroff — firmware launcher does that on exit 10.
    quit_powers_off: bool = False

    model_path: Path = field(default_factory=lambda: MODEL_PATH)
    # --demo: force synthetic depth/IR (no freenect open). Lab / VM UI test.
    allow_demo_without_kinect: bool = False

    def apply_field_lite(self) -> None:
        """Atom / 2 GB preset: lower live+record FPS, skip pose some frames (#14)."""
        self.field_lite = True
        self.target_fps = float(FIELD_LITE_TARGET_FPS)
        self.record_fps = float(FIELD_LITE_RECORD_FPS)
        self.pose_every_n_frames = int(FIELD_LITE_POSE_EVERY_N)
        self.max_poses = 1
        self.clamp_max_poses()
        self.display_fast = True
        # FPS logging off by default — periodic print + session jsonl was for
        # temporary #14 QA and adds I/O on Atom. Opt-in: SLS_SHOW_FPS=1 (bar only)
        # or SLS_FPS_LOG_INTERVAL=N for rare lab debugging.
        self.fps_log_interval_s = 0.0

    def apply_perf_from_env(self) -> None:
        """SLS_* env overrides (firmware launcher). Call after CLI flags."""
        raw = (os.environ.get("SLS_FIELD_LITE") or "").strip().lower()
        if raw in ("1", "true", "yes", "on", "lite"):
            self.apply_field_lite()

        def _float(name: str) -> Optional[float]:
            v = (os.environ.get(name) or "").strip()
            if not v:
                return None
            try:
                return float(v)
            except ValueError:
                return None

        def _int(name: str) -> Optional[int]:
            v = (os.environ.get(name) or "").strip()
            if not v:
                return None
            try:
                return int(float(v))
            except ValueError:
                return None

        tf = _float("SLS_TARGET_FPS")
        if tf is not None and tf > 0:
            self.target_fps = max(1.0, min(60.0, tf))
        rf = _float("SLS_RECORD_FPS")
        if rf is not None and rf > 0:
            self.record_fps = max(1.0, min(60.0, rf))
        pe = _int("SLS_POSE_EVERY_N")
        if pe is not None and pe >= 1:
            self.pose_every_n_frames = min(30, pe)

        df = (os.environ.get("SLS_DISPLAY_FAST") or "").strip().lower()
        if df in ("1", "true", "yes", "on", "fast"):
            self.display_fast = True
        elif df in ("0", "false", "no", "off", "smooth"):
            self.display_fast = False

        sf = (os.environ.get("SLS_SHOW_FPS") or "").strip().lower()
        if sf in ("1", "true", "yes", "on"):
            self.show_fps = True
        elif sf in ("0", "false", "no", "off"):
            self.show_fps = False

        li = _float("SLS_FPS_LOG_INTERVAL")
        if li is not None:
            self.fps_log_interval_s = max(0.0, li)

        rf = (os.environ.get("SLS_RECORD_MP4") or os.environ.get("SLS_RECORD_FORMAT") or "").strip().lower()
        if rf in ("1", "true", "yes", "on", "mp4"):
            self.record_format = "mp4"
        elif rf in ("0", "false", "no", "off", "avi"):
            self.record_format = "avi"

        he = (os.environ.get("SLS_HARDWARE_ENCODE") or "").strip().lower()
        if he in ("1", "true", "yes", "on", "vaapi", "hw"):
            self.hardware_encode = True
        elif he in ("0", "false", "no", "off"):
            self.hardware_encode = False

    def wants_mp4(self) -> bool:
        return (self.record_format or "avi").strip().lower() == "mp4"

    def perf_summary(self) -> str:
        h264 = self.h264_encoder or "?"
        return (
            f"target_fps={self.target_fps:g} record_fps={self.record_fps:g} "
            f"record_format={self.record_format} h264={h264} "
            f"hw_encode={int(self.hardware_encode)} "
            f"pose_every={self.pose_every_n_frames} field_lite={self.field_lite} "
            f"display_fast={self.display_fast} show_fps={self.show_fps}"
        )

    def load_persisted(self, path: Path = SETTINGS_PATH) -> None:
        if not path.is_file():
            self._apply_quit_env_override()
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._apply_quit_env_override()
            return
        if not isinstance(data, dict):
            self._apply_quit_env_override()
            return
        for key in PERSIST_KEYS:
            if key in data:
                setattr(self, key, data[key])
        # Migrate older preference key
        if "drakevox_enabled" not in data and "ovilus_enabled" in data:
            self.drakevox_enabled = bool(data["ovilus_enabled"])
        self.mirror = bool(self.mirror)
        self.spectrum_enabled = bool(self.spectrum_enabled)
        self.spectrum_style = normalize_spectrum_style(
            str(getattr(self, "spectrum_style", DEFAULT_SPECTRUM_STYLE) or "")
        )
        self.auto_snap_on_detect = bool(self.auto_snap_on_detect)
        self.drakevox_enabled = bool(self.drakevox_enabled)
        self.drakevox_on_autosnap = bool(self.drakevox_on_autosnap)
        # Ignore legacy quit_powers_off / keep_display_on keys in JSON
        ct = str(getattr(self, "captures_target", "local") or "local").lower().strip()
        self.captures_target = "auto" if ct == "auto" else "local"
        if self.display_brightness is not None:
            try:
                self.display_brightness = int(self.display_brightness)
                self.display_brightness = max(5, min(100, self.display_brightness))
            except (TypeError, ValueError):
                self.display_brightness = None
        self.clamp_pose_confidence()
        self.clamp_max_poses()
        # IR gain is not user-persisted; always full sensor gain (50)
        self.ir_brightness = 50
        # Firmware env only (never disk) for power-off intent
        self._apply_quit_env_override()

    def _apply_quit_env_override(self) -> None:
        """SLS_QUIT_ACTION from firmware; default False on bare ./run.sh."""
        forced = env_wants_poweroff_on_quit()
        if forced is not None:
            self.quit_powers_off = bool(forced)
        else:
            self.quit_powers_off = False

    def clamp_pose_confidence(self) -> None:
        lo, hi = float(self.pose_conf_min), float(self.pose_conf_max)
        step = float(self.pose_conf_step) or 0.05
        v = float(self.pose_min_confidence)
        # Snap to step grid from lo so +/− never lands on 0.99 / 0.94 orphans
        n = round((v - lo) / step)
        v = lo + n * step
        v = max(lo, min(hi, round(v, 2)))
        self.pose_min_confidence = float(v)
        # Drawing threshold tracks confidence (slightly looser so limbs still connect)
        self.skeleton_min_vis = max(0.20, self.pose_min_confidence - 0.10)

    def clamp_max_poses(self) -> None:
        lo, hi = int(self.max_poses_min), int(self.max_poses_max)
        self.max_poses = int(max(lo, min(hi, int(self.max_poses))))

    def reset_pose_defaults(self) -> None:
        """Restore MediaPipe pose defaults + field defaults (captures Auto, phosphor)."""
        self.pose_min_confidence = float(MEDIAPIPE_DEFAULT_CONFIDENCE)
        self.max_poses = int(MEDIAPIPE_DEFAULT_MAX_POSES)
        self.clamp_pose_confidence()
        self.clamp_max_poses()
        # Captures: prefer USB/SD when present
        self.captures_target = "auto"
        # Spectrum look: phosphor scope trail
        self.spectrum_style = DEFAULT_SPECTRUM_STYLE
        self.save_persisted()

    def save_persisted(self, path: Path = SETTINGS_PATH) -> None:
        self.clamp_pose_confidence()
        self.clamp_max_poses()
        self.spectrum_style = normalize_spectrum_style(self.spectrum_style)
        data: Dict[str, Any] = {
            "mirror": bool(self.mirror),
            "pose_min_confidence": float(self.pose_min_confidence),
            "max_poses": int(self.max_poses),
            "spectrum_enabled": bool(self.spectrum_enabled),
            "spectrum_style": str(self.spectrum_style),
            "auto_snap_on_detect": bool(self.auto_snap_on_detect),
            "drakevox_enabled": bool(self.drakevox_enabled),
            "drakevox_on_autosnap": bool(self.drakevox_on_autosnap),
            "display_brightness": (
                int(self.display_brightness)
                if self.display_brightness is not None
                else None
            ),
            "captures_target": str(self.captures_target or "local"),
        }
        try:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass


settings = Settings()
settings.load_persisted()
