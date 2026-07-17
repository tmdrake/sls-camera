"""Session snapshot, recording, and light anomaly log."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .config import VIEWER_ROOT

CAPTURES_DIR = VIEWER_ROOT / "captures"


class SessionRecorder:
    def __init__(self, captures_dir: Path = CAPTURES_DIR):
        self.captures_dir = Path(captures_dir)
        self._lock = threading.Lock()
        self._writer: Optional[cv2.VideoWriter] = None
        self._path: Optional[Path] = None
        self._recording = False
        self._fps = 15.0
        self._record_started: float = 0.0
        self._last_detected = 0
        self._session_log: Optional[Path] = None
        self._flash = ""
        self._flash_until = 0.0

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def recording_elapsed_s(self) -> float:
        if not self._recording or self._record_started <= 0:
            return 0.0
        return max(0.0, time.time() - self._record_started)

    def recording_elapsed_str(self) -> str:
        """Wall-clock elapsed as M:SS or H:MM:SS."""
        sec = int(self.recording_elapsed_s())
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def flash_message(self) -> str:
        if time.time() < self._flash_until:
            return self._flash
        return ""

    def _set_flash(self, msg: str, seconds: float = 2.5) -> None:
        self._flash = msg
        self._flash_until = time.time() + seconds

    def ensure_dir(self) -> Path:
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        return self.captures_dir

    def _ts(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def snapshot(self, bgr: np.ndarray) -> Optional[Path]:
        if bgr is None or bgr.size == 0:
            self._set_flash("snapshot failed: no frame")
            return None
        self.ensure_dir()
        path = self.captures_dir / f"sls_{self._ts()}.jpg"
        ok = cv2.imwrite(str(path), bgr)
        if ok:
            self._set_flash(f"saved {path.name}")
            self._log_event("snapshot", {"file": path.name})
            return path
        self._set_flash("snapshot failed: write error")
        return None

    def start_record(self, bgr: np.ndarray, fps: float = 15.0) -> Optional[Path]:
        if self._recording:
            return self._path
        if bgr is None or bgr.size == 0:
            self._set_flash("record failed: no frame")
            return None
        self.ensure_dir()
        h, w = bgr.shape[:2]
        path = self.captures_dir / f"sls_{self._ts()}.avi"
        # MJPG in AVI is widely available via OpenCV builds
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(str(path), fourcc, float(fps), (w, h))
        if not writer.isOpened():
            self._set_flash("record failed: codec")
            return None
        with self._lock:
            self._writer = writer
            self._path = path
            self._recording = True
            self._fps = float(fps)
            self._record_started = time.time()
        self._set_flash(f"recording {path.name}")
        self._log_event("record_start", {"file": path.name})
        return path

    def write_frame(self, bgr: np.ndarray) -> None:
        if not self._recording or bgr is None:
            return
        with self._lock:
            w = self._writer
        if w is None:
            return
        try:
            w.write(bgr)
        except Exception:
            pass

    def stop_record(self) -> Optional[Path]:
        path = self._path
        elapsed = self.recording_elapsed_str() if self._recording else "0:00"
        with self._lock:
            if self._writer is not None:
                try:
                    self._writer.release()
                except Exception:
                    pass
            self._writer = None
            self._recording = False
            self._record_started = 0.0
        if path:
            self._set_flash(f"saved {path.name} ({elapsed})")
            self._log_event(
                "record_stop", {"file": path.name, "elapsed": elapsed}
            )
        return path

    def _log_path(self) -> Path:
        if self._session_log is None:
            self.ensure_dir()
            self._session_log = self.captures_dir / f"session_{self._ts()}.jsonl"
        return self._session_log

    def _log_event(self, kind: str, extra: Optional[dict] = None) -> None:
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": kind,
        }
        if extra:
            rec.update(extra)
        try:
            path = self._log_path()
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    def note_detection(self, detected: int, auto_snap: bool, bgr: Optional[np.ndarray]) -> None:
        """Call each UI tick with current poses_count for edge anomalies."""
        prev = self._last_detected
        cur = int(detected)
        if cur > 0 and prev == 0:
            self._log_event("detect_appear", {"detected": cur})
            if auto_snap and bgr is not None:
                self.snapshot(bgr)
        elif cur == 0 and prev > 0:
            self._log_event("detect_disappear", {"detected": 0})
        self._last_detected = cur
