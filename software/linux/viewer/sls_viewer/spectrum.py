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
        self._stream = None
        self._running = False
        self._want_enabled = False
        self._device_name = ""
        self._error = ""
        self._last_retry = 0.0
        self._cb_errors = 0
        self._pcm_sinks: List[PcmSink] = []

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
        img[:] = (12, 12, 12)
        levels = self.levels()
        n = len(levels)
        if n < 1 or width < 8 or height < 4:
            return img
        gap = 1
        bar_w = max(1, (width - gap * (n + 1)) // n)
        for i, v in enumerate(levels):
            h = int(max(0.0, min(1.0, float(v))) * (height - 4))
            x0 = gap + i * (bar_w + gap)
            x1 = min(width - 1, x0 + bar_w)
            y0 = height - 2 - h
            y1 = height - 2
            color = (0, int(180 + 75 * v), int(120 + 100 * v))
            cv2.rectangle(img, (x0, y0), (x1, y1), color, -1)
        cv2.line(img, (0, height - 2), (width - 1, height - 2), (40, 40, 40), 1)
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
                (70, 70, 70),
                1,
                cv2.LINE_AA,
            )
        return img
