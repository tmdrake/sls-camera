"""Mic capture + FFT bars for the SLS spectrum strip.

Prefers Kinect USB Audio (after kinect-audio-setup); falls back to default.
Retries open when the device drops (unplug / power cycle).
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

import numpy as np

from .audio_device import pick_input_device

# Optional PCM sinks (e.g. SessionRecorder) share this stream — one open of the mic.
PcmSink = Callable[[np.ndarray], None]


class SpectrumAnalyzer:
    def __init__(
        self,
        sample_rate: int = 16000,
        block_size: int = 1024,
        n_bars: int = 48,
        retry_interval_s: float = 2.0,
    ):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.n_bars = n_bars
        self.retry_interval_s = retry_interval_s
        self._lock = threading.Lock()
        self._levels = np.zeros(n_bars, dtype=np.float32)
        # Phosphor / scope trail: peak envelope decays slower than live bars
        self._peaks = np.zeros(n_bars, dtype=np.float32)
        self._peak_hold_until = np.zeros(n_bars, dtype=np.float64)
        self._last_paint_t = 0.0
        self._stream = None
        self._running = False
        self._want_enabled = False
        self._device_name = ""
        self._error = ""
        self._last_retry = 0.0
        self._cb_errors = 0
        self._pcm_sinks: List[PcmSink] = []

    # Peak hold then fall (seconds / fall rate) — CRT-ish scope feel
    _PEAK_HOLD_S = 0.14
    _PEAK_DECAY_PER_S = 1.35

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def error(self) -> str:
        return self._error

    @property
    def active(self) -> bool:
        return self._running and self._stream is not None

    def levels(self) -> np.ndarray:
        with self._lock:
            return self._levels.copy()

    def _update_peaks_unlocked(self, levels: np.ndarray, now: float) -> np.ndarray:
        """Raise peaks with levels; hold briefly; then decay (phosphor trail)."""
        n = min(len(levels), len(self._peaks))
        if n < 1:
            return self._peaks.copy()
        lv = levels[:n]
        pk = self._peaks[:n]
        hold = self._peak_hold_until[:n]
        # New peaks
        risen = lv > pk
        pk = np.where(risen, lv, pk)
        hold = np.where(risen, now + self._PEAK_HOLD_S, hold)
        # Decay after hold
        dt = 0.0
        if self._last_paint_t > 0:
            dt = max(0.0, min(0.1, now - self._last_paint_t))
        if dt > 0:
            falling = now > hold
            pk = np.where(
                falling,
                np.maximum(lv, pk - self._PEAK_DECAY_PER_S * dt),
                pk,
            )
        self._peaks[:n] = pk
        self._peak_hold_until[:n] = hold
        self._last_paint_t = now
        return pk.copy()

    def start(self) -> bool:
        self._want_enabled = True
        return self._open_stream()

    def stop(self) -> None:
        self._want_enabled = False
        self._close_stream()

    def ensure_running(self) -> None:
        """Call from UI tick: reopen mic if enabled/sunk but dead."""
        need = self._want_enabled or bool(self._pcm_sinks)
        if not need:
            return
        if self.active:
            return
        now = time.time()
        if now - self._last_retry < self.retry_interval_s:
            return
        self._last_retry = now
        self._close_stream()
        self._open_stream()

    def add_pcm_sink(self, sink: PcmSink) -> None:
        """Share live mic PCM with a recorder (avoids second exclusive open)."""
        with self._lock:
            if sink not in self._pcm_sinks:
                self._pcm_sinks.append(sink)
        self.ensure_running()

    def remove_pcm_sink(self, sink: PcmSink) -> None:
        with self._lock:
            self._pcm_sinks = [s for s in self._pcm_sinks if s is not sink]
        if not self._want_enabled and not self._pcm_sinks:
            self._close_stream()

    def _close_stream(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _open_stream(self) -> bool:
        if self._running and self._stream is not None:
            return True
        self._error = ""
        try:
            import sounddevice as sd
        except Exception as e:
            self._error = f"sounddevice missing: {e}"
            return False

        device, label = pick_input_device(sd)
        self._device_name = label or "default"

        def callback(indata, frames, time_info, status):
            if status:
                self._cb_errors += 1
                # Too many stream status problems → force reopen next ensure_running
                if self._cb_errors > 30:
                    self._running = False
            try:
                mono = indata[:, 0].astype(np.float32)
                with self._lock:
                    sinks = list(self._pcm_sinks)
                for sink in sinks:
                    try:
                        sink(mono)
                    except Exception:
                        pass
                window = np.hanning(len(mono))
                spec = np.abs(np.fft.rfft(mono * window))
                edges = np.linspace(1, len(spec), self.n_bars + 1, dtype=int)
                bars = np.zeros(self.n_bars, dtype=np.float32)
                for b in range(self.n_bars):
                    lo, hi = edges[b], max(edges[b] + 1, edges[b + 1])
                    chunk = spec[lo:hi]
                    if chunk.size:
                        bars[b] = float(np.mean(chunk))
                bars = np.log1p(bars * 20.0)
                peak = float(bars.max()) if bars.size else 1.0
                if peak > 1e-6:
                    bars = bars / peak
                with self._lock:
                    self._levels = 0.65 * self._levels + 0.35 * bars
            except Exception:
                pass

        try:
            kwargs = dict(
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                dtype="float32",
                callback=callback,
            )
            if device is not None:
                kwargs["device"] = device
            self._stream = sd.InputStream(**kwargs)
            self._stream.start()
            self._running = True
            self._cb_errors = 0
            return True
        except Exception as e:
            self._error = str(e)
            self._stream = None
            self._running = False
            return False

    def paint_bgr(self, width: int, height: int) -> np.ndarray:
        import cv2

        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = (10, 14, 12)
        with self._lock:
            levels = self._levels.copy()
            now = time.time()
            peaks = self._update_peaks_unlocked(levels, now)
        n = len(levels)
        if n < 1 or width < 8 or height < 4:
            return img

        usable_h = max(1, height - 4)
        gap = 1
        bar_w = max(1, (width - gap * (n + 1)) // n)
        baseline = height - 2

        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            p = float(max(0.0, min(1.0, peaks[i] if i < len(peaks) else v)))
            h_live = int(v * usable_h)
            h_peak = int(p * usable_h)
            x0 = gap + i * (bar_w + gap)
            x1 = min(width - 1, x0 + bar_w)
            if x1 <= x0:
                continue

            # Ghost column (phosphor trail) up to peak — dimmer SLS green
            if h_peak > 0:
                y_peak = baseline - h_peak
                trail = (
                    0,
                    int(40 + 90 * p),
                    int(25 + 55 * p),
                )
                cv2.rectangle(img, (x0, y_peak), (x1, baseline), trail, -1)

            # Live bar (bright core) on top of trail
            if h_live > 0:
                y_live = baseline - h_live
                core = (
                    0,
                    int(160 + 95 * v),
                    int(100 + 120 * v),
                )
                cv2.rectangle(img, (x0, y_live), (x1, baseline), core, -1)

            # Peak cap (scope marker) — short bright tick at envelope top
            if h_peak > 1:
                y_cap = baseline - h_peak
                cap = (40, 255, 200)
                y1_cap = min(baseline, y_cap + max(1, min(2, bar_w)))
                cv2.rectangle(img, (x0, y_cap), (x1, y1_cap), cap, -1)

        # Baseline (scope ground)
        cv2.line(img, (0, baseline), (width - 1, baseline), (35, 55, 45), 1)

        if not self.active:
            msg = "reconnecting mic…" if self._want_enabled else "spectrum off"
            if self._error and self._want_enabled:
                msg = "mic retry…"
            cv2.putText(
                img,
                msg,
                (8, max(12, height // 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (80, 80, 80),
                1,
                cv2.LINE_AA,
            )
        elif self._device_name:
            cv2.putText(
                img,
                self._device_name[:40],
                (6, 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (55, 90, 70),
                1,
                cv2.LINE_AA,
            )
        return img
