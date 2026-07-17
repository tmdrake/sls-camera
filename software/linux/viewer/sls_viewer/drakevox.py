"""DrakeVox random-word panel (field spirit-box style word generator).

Renamed from the old Windows "Ovilus" label for trademark safety.
Timer: random 5–15 min between words; each hit is timestamped.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

DEFAULT_WORDS: Tuple[str, ...] = (
    "SPIRIT",
    "GHOST",
    "SHADOW",
    "CHILD",
    "WOMAN",
    "MAN",
    "DEMON",
    "ANGEL",
    "LEAVE",
    "STAY",
    "HELP",
    "HERE",
    "COLD",
    "ENERGY",
    "YES",
    "NO",
    "DARK",
    "LIGHT",
    "FOLLOW",
    "GO",
)

MIN_INTERVAL_S = 5 * 60
MAX_INTERVAL_S = 15 * 60
HISTORY_MAX = 12
OVERLAY_HISTORY_N = 5


@dataclass
class DrakeVoxEvent:
    ts: float
    word: str

    def time_str(self) -> str:
        return datetime.fromtimestamp(self.ts).strftime("%H:%M:%S")

    def label(self) -> str:
        return f"{self.time_str()} — {self.word}"


class DrakeVoxEngine:
    """Thread-safe timer + word state for the Qt field UI."""

    def __init__(
        self,
        words: Sequence[str] = DEFAULT_WORDS,
        min_interval_s: float = MIN_INTERVAL_S,
        max_interval_s: float = MAX_INTERVAL_S,
        history_max: int = HISTORY_MAX,
        enabled: bool = True,
    ):
        self.words = tuple(w.upper() for w in words if w.strip())
        self.min_interval_s = float(min_interval_s)
        self.max_interval_s = float(max_interval_s)
        self.history_max = int(history_max)
        self._lock = threading.Lock()
        self._enabled = bool(enabled)
        self._current = ""
        self._history: List[DrakeVoxEvent] = []
        self._next_at = 0.0
        self._last_fire_at = 0.0
        self._schedule_next_unlocked(from_now=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        with self._lock:
            was = self._enabled
            self._enabled = bool(value)
            if self._enabled and not was:
                self._schedule_next_unlocked(from_now=True)

    @property
    def current(self) -> str:
        with self._lock:
            return self._current

    @property
    def last_fire_at(self) -> float:
        with self._lock:
            return self._last_fire_at

    def history(self) -> List[DrakeVoxEvent]:
        with self._lock:
            return list(self._history)

    def history_lines(self, limit: int = HISTORY_MAX) -> List[str]:
        return [e.label() for e in self.history()[:limit]]

    def tick(self) -> Optional[str]:
        if not self.enabled:
            return None
        with self._lock:
            if time.time() < self._next_at:
                return None
            return self._generate_unlocked()

    def generate_now(self) -> Optional[str]:
        """Manual fire. No-op when disabled (OFF = no generation)."""
        if not self.enabled:
            return None
        with self._lock:
            if not self._enabled:
                return None
            return self._generate_unlocked()

    def flash_active(self, hold_s: float = 8.0) -> bool:
        with self._lock:
            if self._last_fire_at <= 0:
                return False
            return (time.time() - self._last_fire_at) < hold_s

    def _schedule_next_unlocked(self, from_now: bool = True) -> None:
        lo = min(self.min_interval_s, self.max_interval_s)
        hi = max(self.min_interval_s, self.max_interval_s)
        delay = random.uniform(lo, hi)
        base = time.time() if from_now else self._next_at
        self._next_at = base + delay

    def _generate_unlocked(self) -> str:
        word = random.choice(self.words) if self.words else "—"
        now = time.time()
        self._current = word
        self._last_fire_at = now
        self._history.insert(0, DrakeVoxEvent(ts=now, word=word))
        if len(self._history) > self.history_max:
            self._history = self._history[: self.history_max]
        self._schedule_next_unlocked(from_now=True)
        return word


def paint_drakevox_bgr(
    bgr,
    *,
    enabled: bool,
    flash: bool = False,
    history: Optional[Sequence[DrakeVoxEvent]] = None,
    pip_w: int = 280,
    pip_h: int = 210,
    pip_margin: int = 12,
    pip_corner: str = "top-right",
    history_n: int = OVERLAY_HISTORY_N,
) -> None:
    """Draw DrakeVox panel under IR PiP: last N words with timestamps.

    When enabled is False, draws nothing (Settings ON/OFF show/hide).
    """
    import cv2

    if not enabled:
        return
    if bgr is None or bgr.size == 0:
        return
    h, w = bgr.shape[:2]
    if w < 80 or h < 40:
        return

    n_show = max(1, int(history_n))
    events: List[DrakeVoxEvent] = list(history or [])[:n_show]

    margin = max(0, int(pip_margin))
    box_w = max(80, min(int(pip_w), w - 2 * margin))
    title_h = 22
    row_h = 26
    pad_y = 10
    box_h = title_h + pad_y + n_show * row_h + 12
    gap = 6

    if str(pip_corner).lower() in ("top-left", "left"):
        x0 = margin
    else:
        x0 = w - box_w - margin
    y0 = margin + max(60, int(pip_h)) + gap
    if y0 + box_h > h - 8:
        y0 = max(margin, h - box_h - 8)
    x1, y1 = x0 + box_w, y0 + box_h

    overlay = bgr.copy()
    color_bg = (28, 12, 48) if flash else (14, 14, 18)
    cv2.rectangle(overlay, (x0, y0), (x1, y1), color_bg, -1)
    border = (0, 0, 220) if flash else (60, 40, 40)
    cv2.rectangle(overlay, (x0, y0), (x1, y1), border, 1)
    cv2.line(overlay, (x0, y0), (x1, y0), (0, 255, 180), 1)
    alpha = 0.78 if flash else 0.62
    cv2.addWeighted(overlay, alpha, bgr, 1.0 - alpha, 0, bgr)

    cv2.putText(
        bgr,
        "DRAKEVOX",
        (x0 + 8, y0 + 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (0, 90, 220),
        1,
        cv2.LINE_AA,
    )

    text_y = y0 + title_h + pad_y
    if not events:
        cv2.putText(
            bgr,
            "…",
            (x0 + 8, text_y + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (120, 120, 120),
            1,
            cv2.LINE_AA,
        )
        return

    for i, ev in enumerate(events):
        is_latest = i == 0
        label = f"{ev.time_str()} {ev.word}"
        if is_latest:
            scale = 0.58 if flash else 0.52
            color = (0, 0, 220)
            thick = 2
        else:
            scale = 0.45
            fade = max(70, 160 - i * 22)
            color = (fade, fade, fade)
            thick = 1
        max_chars = max(8, box_w // 8)
        if len(label) > max_chars:
            label = label[: max_chars - 1] + "…"
        cv2.putText(
            bgr,
            label,
            (x0 + 8, text_y + i * row_h),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thick,
            cv2.LINE_AA,
        )
