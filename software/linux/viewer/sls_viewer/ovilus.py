"""Ovilus random-word panel — Windows parity (15–30 min timer).

Windows reference: software/source/example/KinectWindow.xaml.cs
  - word list, Timer 900000 ms then 900000 + rand(900000)
  - history capped at 12
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

# Same vocabulary as the Windows SLS Explorer
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

# Windows: 15 min base, +0..15 min random → 15–30 min between words
MIN_INTERVAL_S = 15 * 60
MAX_INTERVAL_S = 30 * 60
HISTORY_MAX = 12


@dataclass
class OvilusEvent:
    ts: float
    word: str

    def label(self) -> str:
        t = datetime.fromtimestamp(self.ts).strftime("%H:%M:%S")
        return f"{t} — {self.word}"


class OvilusEngine:
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
        self._history: List[OvilusEvent] = []
        self._next_at = 0.0
        self._last_fire_at = 0.0
        self._schedule_next(from_now=True)

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

    def seconds_until_next(self) -> float:
        with self._lock:
            if not self._enabled:
                return float("inf")
            return max(0.0, self._next_at - time.time())

    def next_eta_str(self) -> str:
        sec = self.seconds_until_next()
        if not self.enabled:
            return "off"
        if sec == float("inf"):
            return "—"
        m = int(sec // 60)
        s = int(sec % 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"{h}h{m:02d}m"
        return f"{m}:{s:02d}"

    def history(self) -> List[OvilusEvent]:
        with self._lock:
            return list(self._history)

    def history_lines(self, limit: int = HISTORY_MAX) -> List[str]:
        return [e.label() for e in self.history()[:limit]]

    def tick(self) -> Optional[str]:
        """Call from UI loop. Returns a new word if the timer just fired."""
        if not self.enabled:
            return None
        with self._lock:
            if time.time() < self._next_at:
                return None
            return self._generate_unlocked()

    def generate_now(self) -> str:
        """Manual / Settings trigger (also reschedules the random timer)."""
        with self._lock:
            return self._generate_unlocked()

    def flash_active(self, hold_s: float = 8.0) -> bool:
        """True briefly after a word so UI can emphasize it."""
        with self._lock:
            if self._last_fire_at <= 0:
                return False
            return (time.time() - self._last_fire_at) < hold_s

    def _schedule_next(self, from_now: bool = True) -> None:
        with self._lock:
            self._schedule_next_unlocked(from_now=from_now)

    def _schedule_next_unlocked(self, from_now: bool = True) -> None:
        lo = min(self.min_interval_s, self.max_interval_s)
        hi = max(self.min_interval_s, self.max_interval_s)
        delay = random.uniform(lo, hi)
        base = time.time() if from_now else self._next_at
        self._next_at = base + delay

    def _generate_unlocked(self) -> str:
        if not self.words:
            word = "—"
        else:
            word = random.choice(self.words)
        now = time.time()
        self._current = word
        self._last_fire_at = now
        self._history.insert(0, OvilusEvent(ts=now, word=word))
        if len(self._history) > self.history_max:
            self._history = self._history[: self.history_max]
        self._schedule_next_unlocked(from_now=True)
        return word


def paint_ovilus_bgr(
    bgr,
    word: str,
    *,
    enabled: bool,
    flash: bool = False,
    eta: str = "",
) -> None:
    """Draw Ovilus badge bottom-left (in-place). Empty word → quiet idle label."""
    import cv2
    import numpy as np

    if bgr is None or bgr.size == 0:
        return
    h, w = bgr.shape[:2]
    if w < 80 or h < 40:
        return

    # Banner geometry
    pad = 10
    box_h = 72 if flash else 56
    box_w = min(w - 2 * pad, 360 if word else 200)
    x0, y0 = pad, h - box_h - pad - 8
    x1, y1 = x0 + box_w, y0 + box_h

    overlay = bgr.copy()
    color_bg = (20, 10, 40) if flash else (16, 16, 16)
    cv2.rectangle(overlay, (x0, y0), (x1, y1), color_bg, -1)
    border = (0, 0, 200) if flash else (80, 40, 40)
    cv2.rectangle(overlay, (x0, y0), (x1, y1), border, 1)
    alpha = 0.72 if flash else 0.55
    cv2.addWeighted(overlay, alpha, bgr, 1.0 - alpha, 0, bgr)

    title = "OVILUS" if enabled else "OVILUS OFF"
    cv2.putText(
        bgr,
        title,
        (x0 + 10, y0 + 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 80, 200) if enabled else (90, 90, 90),
        1,
        cv2.LINE_AA,
    )
    if enabled and word:
        scale = 1.15 if flash else 0.95
        thickness = 2 if flash else 2
        cv2.putText(
            bgr,
            word,
            (x0 + 10, y0 + 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 200),  # BGR red-ish like Windows #AA0000
            thickness,
            cv2.LINE_AA,
        )
    elif enabled:
        cv2.putText(
            bgr,
            f"next {eta}" if eta else "…",
            (x0 + 10, y0 + 46),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (120, 120, 120),
            1,
            cv2.LINE_AA,
        )
