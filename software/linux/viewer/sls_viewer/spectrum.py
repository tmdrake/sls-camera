"""Mic capture + FFT bars for the SLS spectrum strip.

Prefers Kinect USB Audio (after kinect-audio-setup firmware load);
falls back to default system capture device.
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional, Tuple

import numpy as np

# Prefer these name fragments when picking a capture device (case-insensitive)
_KINECT_HINTS = (
    "kinect",
    "xbox",
    "nui",
    "microsoft",
    "usb audio",
    "usb-audio",
    "uac",
)


class SpectrumAnalyzer:
    def __init__(
        self,
        sample_rate: int = 16000,
        block_size: int = 1024,
        n_bars: int = 48,
    ):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.n_bars = n_bars
        self._lock = threading.Lock()
        self._levels = np.zeros(n_bars, dtype=np.float32)
        self._stream = None
        self._running = False
        self._device_name = ""
        self._error = ""
        self._enabled = False

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

    def _pick_device(self, sd) -> Tuple[Optional[int], str]:
        """Return (device_index or None for default, label)."""
        try:
            devices = sd.query_devices()
        except Exception as e:
            self._error = str(e)
            return None, ""

        best_i: Optional[int] = None
        best_name = ""
        for i, d in enumerate(devices):
            if int(d.get("max_input_channels", 0) or 0) < 1:
                continue
            name = str(d.get("name", ""))
            low = name.lower()
            if any(h in low for h in _KINECT_HINTS):
                best_i = i
                best_name = name
                break
        if best_i is not None:
            return best_i, best_name
        try:
            default = sd.default.device[0]
            name = str(devices[default]["name"]) if default is not None else "default"
            return default, name
        except Exception:
            return None, "default"

    def start(self) -> bool:
        if self._running:
            return True
        self._error = ""
        try:
            import sounddevice as sd
        except Exception as e:
            self._error = f"sounddevice missing: {e}"
            return False

        device, label = self._pick_device(sd)
        self._device_name = label or "default"

        def callback(indata, frames, time_info, status):
            if status:
                pass
            try:
                mono = indata[:, 0].astype(np.float32)
                # Hann window + rFFT
                window = np.hanning(len(mono))
                spec = np.abs(np.fft.rfft(mono * window))
                # Group into bars (skip DC-ish bin 0)
                n = max(1, len(spec) - 1)
                edges = np.linspace(1, len(spec), self.n_bars + 1, dtype=int)
                bars = np.zeros(self.n_bars, dtype=np.float32)
                for b in range(self.n_bars):
                    lo, hi = edges[b], max(edges[b] + 1, edges[b + 1])
                    chunk = spec[lo:hi]
                    if chunk.size:
                        bars[b] = float(np.mean(chunk))
                # Log-ish scale + smooth
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
            self._enabled = True
            return True
        except Exception as e:
            self._error = str(e)
            self._stream = None
            self._running = False
            return False

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def paint_bgr(self, width: int, height: int) -> np.ndarray:
        """Render dark strip with cyan bars (OpenCV BGR)."""
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
            # Cyan/green SLS palette
            color = (0, int(180 + 75 * v), int(120 + 100 * v))
            cv2.rectangle(img, (x0, y0), (x1, y1), color, -1)
        # baseline
        cv2.line(img, (0, height - 2), (width - 1, height - 2), (40, 40, 40), 1)
        if self._error and not self.active:
            cv2.putText(
                img,
                "spectrum off",
                (8, max(12, height // 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (80, 80, 80),
                1,
                cv2.LINE_AA,
            )
        elif self._device_name:
            label = self._device_name[:40]
            cv2.putText(
                img,
                label,
                (6, 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (70, 70, 70),
                1,
                cv2.LINE_AA,
            )
        return img
