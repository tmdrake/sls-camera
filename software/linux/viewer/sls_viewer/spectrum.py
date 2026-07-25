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

# Visual styles for the strip (Settings cycle; default phosphor).
# glow / waterfall cost a bit more CPU than bar styles, but the strip is
# only ~56px tall so they stay light on Atom tablets.
# win98 = time-domain oscilloscope (raw PCM), not FFT bars.
SPECTRUM_STYLES = (
    "phosphor",
    "classic",
    "mirror",
    "heat",
    "bands",
    "grid",
    "wave",
    "win98",
    "glow",
    "dots",
    "waterfall",
)
SPECTRUM_STYLE_LABELS = {
    "phosphor": "Phosphor",
    "classic": "Classic",
    "mirror": "Mirror",
    "heat": "Heat tips",
    "bands": "Freq bands",
    "grid": "Scope grid",
    "wave": "Wave",
    "win98": "Win98 wave",
    "glow": "Glow",
    "dots": "Dots",
    "waterfall": "Waterfall",
}
DEFAULT_SPECTRUM_STYLE = "phosphor"


def normalize_spectrum_style(style: Optional[str]) -> str:
    s = (style or DEFAULT_SPECTRUM_STYLE).strip().lower()
    if s in SPECTRUM_STYLES:
        return s
    return DEFAULT_SPECTRUM_STYLE


def spectrum_style_label(style: Optional[str]) -> str:
    sid = normalize_spectrum_style(style)
    return SPECTRUM_STYLE_LABELS.get(sid, SPECTRUM_STYLE_LABELS[DEFAULT_SPECTRUM_STYLE])


def next_spectrum_style(style: Optional[str]) -> str:
    sid = normalize_spectrum_style(style)
    i = SPECTRUM_STYLES.index(sid)
    return SPECTRUM_STYLES[(i + 1) % len(SPECTRUM_STYLES)]


class SpectrumAnalyzer:
    def __init__(
        self,
        sample_rate: int = 16000,
        block_size: int = 1024,
        n_bars: int = 64,
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
        # Waterfall: recent frames as rows (freq = columns); small strip → cheap
        self._waterfall_rows: int = 64
        self._waterfall = np.zeros((self._waterfall_rows, n_bars), dtype=np.float32)
        self._waterfall_i = 0
        # Time-domain ring for Win98 / oscilloscope styles (no FFT)
        self._wave_len: int = 2048
        self._wave = np.zeros(self._wave_len, dtype=np.float32)
        self._wave_i = 0
        self._stream = None
        self._running = False
        self._want_enabled = False
        self._device_name = ""
        self._error = ""
        self._last_retry = 0.0
        self._cb_errors = 0
        # Last PortAudio callback time — detect frozen stream after USB drop (#19)
        self._last_pcm_ts = 0.0
        self._pcm_sinks: List[PcmSink] = []

    # No mic callbacks for this long → force reopen (Kinect unplug/replug)
    _STALE_PCM_S = 2.0

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
        """Call from UI tick: reopen mic if enabled/sunk but dead.

        Also upgrades from non-Kinect (e.g. ALSA \"default\") to Kinect when
        the array appears later — common on KVM after ``vm-kinect-usb.sh``
        reattach, or tablet USB late plug. Not related to RCA SST/speakers.

        After Kinect USB unplug the PortAudio stream can stay "open" with no
        callbacks (#19) — levels freeze. Stale PCM forces close+reopen.
        """
        need = self._want_enabled or bool(self._pcm_sinks)
        if not need:
            return
        now = time.time()
        if self.active:
            # Frozen stream: device gone but handle still open (#19)
            if (
                self._last_pcm_ts > 0
                and (now - self._last_pcm_ts) >= self._STALE_PCM_S
                and (now - self._last_retry) >= self.retry_interval_s
            ):
                self._last_retry = now
                self._error = "mic stream stale (USB?); reopening"
                self._close_stream()
                self._open_stream()
                return
            # Sticky wrong device: re-pick when Kinect becomes available
            if now - self._last_retry >= self.retry_interval_s:
                low = (self._device_name or "").lower()
                on_kinect = any(
                    h in low
                    for h in ("kinect", "microsoft", "usb audio", "xbox", "nui", "uac")
                )
                if not on_kinect:
                    try:
                        import sounddevice as sd

                        _dev, label = pick_input_device(sd)
                        lab = (label or "").lower()
                        if any(
                            h in lab
                            for h in ("kinect", "microsoft", "usb audio", "xbox", "nui")
                        ):
                            self._last_retry = now
                            self._close_stream()
                            self._open_stream()
                            return
                    except Exception:
                        pass
                    self._last_retry = now
            return
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
        self._last_pcm_ts = 0.0
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
                self._last_pcm_ts = time.time()
                with self._lock:
                    sinks = list(self._pcm_sinks)
                    # Ring-buffer PCM for time-domain styles (win98 oscilloscope)
                    self._push_wave_unlocked(mono)
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
            # Grace period so ensure_running does not immediately call us stale
            self._last_pcm_ts = time.time()
            return True
        except Exception as e:
            self._error = str(e)
            self._stream = None
            self._running = False
            self._last_pcm_ts = 0.0
            return False

    def paint_bgr(
        self,
        width: int,
        height: int,
        style: str = DEFAULT_SPECTRUM_STYLE,
    ) -> np.ndarray:
        """Draw spectrum strip. ``style`` is a SPECTRUM_STYLES id (default phosphor)."""
        import cv2

        style = normalize_spectrum_style(style)
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = (10, 14, 12)
        with self._lock:
            levels = self._levels.copy()
            now = time.time()
            # Peaks always tracked (used by phosphor/grid/heat; cheap otherwise)
            peaks = self._update_peaks_unlocked(levels, now)
            if style == "waterfall":
                self._push_waterfall_unlocked(levels)
                wf = self._waterfall_snapshot_unlocked()
            else:
                wf = None
            wave_pcm = (
                self._wave_snapshot_unlocked() if style == "win98" else None
            )
        n = len(levels)
        if n < 1 or width < 8 or height < 4:
            self._draw_overlay(img, width, height)
            return img

        if style == "classic":
            self._paint_classic(img, levels, width, height)
        elif style == "mirror":
            self._paint_mirror(img, levels, width, height)
        elif style == "heat":
            self._paint_heat(img, levels, peaks, width, height)
        elif style == "bands":
            self._paint_bands(img, levels, width, height)
        elif style == "grid":
            self._paint_grid(img, levels, peaks, width, height)
        elif style == "wave":
            self._paint_wave(img, levels, width, height)
        elif style == "win98":
            self._paint_win98(img, wave_pcm, width, height)
        elif style == "glow":
            self._paint_glow(img, levels, peaks, width, height)
        elif style == "dots":
            self._paint_dots(img, levels, peaks, width, height)
        elif style == "waterfall":
            self._paint_waterfall(img, wf if wf is not None else levels, width, height)
        else:
            self._paint_phosphor(img, levels, peaks, width, height)

        self._draw_overlay(img, width, height)
        return img

    def _push_wave_unlocked(self, mono: np.ndarray) -> None:
        """Append mono float samples into the time-domain ring (caller holds lock)."""
        x = np.asarray(mono, dtype=np.float32).reshape(-1)
        if x.size < 1:
            return
        n = self._wave_len
        i = int(self._wave_i)
        # Fast path: copy in one or two slices
        for start in range(0, x.size, n):
            chunk = x[start : start + n]
            m = int(chunk.size)
            end = i + m
            if end <= n:
                self._wave[i:end] = chunk
            else:
                k = n - i
                self._wave[i:] = chunk[:k]
                self._wave[: m - k] = chunk[k:]
            i = (i + m) % n
        self._wave_i = i

    def _wave_snapshot_unlocked(self) -> np.ndarray:
        """Oldest→newest mono samples for oscilloscope paint."""
        i = int(self._wave_i) % self._wave_len
        if i == 0:
            return self._wave.copy()
        return np.concatenate((self._wave[i:], self._wave[:i]))

    def _push_waterfall_unlocked(self, levels: np.ndarray) -> None:
        n = min(len(levels), self._waterfall.shape[1])
        row = self._waterfall_i % self._waterfall_rows
        self._waterfall[row, :n] = levels[:n]
        if n < self._waterfall.shape[1]:
            self._waterfall[row, n:] = 0.0
        self._waterfall_i += 1

    def _waterfall_snapshot_unlocked(self) -> np.ndarray:
        """Oldest→newest rows for display (bottom = latest)."""
        i = self._waterfall_i
        rows = self._waterfall_rows
        if i < rows:
            return self._waterfall[: max(1, i)].copy()
        # ring: start at i % rows
        start = i % rows
        return np.vstack((self._waterfall[start:], self._waterfall[:start]))

    def _bar_geom(self, n: int, width: int, height: int):
        usable_h = max(1, height - 4)
        gap = 1
        bar_w = max(1, (width - gap * (n + 1)) // n)
        baseline = height - 2
        return usable_h, gap, bar_w, baseline

    def _paint_phosphor(self, img, levels, peaks, width: int, height: int) -> None:
        import cv2

        n = len(levels)
        usable_h, gap, bar_w, baseline = self._bar_geom(n, width, height)
        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            p = float(max(0.0, min(1.0, peaks[i] if i < len(peaks) else v)))
            h_live = int(v * usable_h)
            h_peak = int(p * usable_h)
            x0 = gap + i * (bar_w + gap)
            x1 = min(width - 1, x0 + bar_w)
            if x1 <= x0:
                continue
            if h_peak > 0:
                trail = (0, int(40 + 90 * p), int(25 + 55 * p))
                cv2.rectangle(
                    img, (x0, baseline - h_peak), (x1, baseline), trail, -1
                )
            if h_live > 0:
                core = (0, int(160 + 95 * v), int(100 + 120 * v))
                cv2.rectangle(
                    img, (x0, baseline - h_live), (x1, baseline), core, -1
                )
            if h_peak > 1:
                y_cap = baseline - h_peak
                y1_cap = min(baseline, y_cap + max(1, min(2, bar_w)))
                cv2.rectangle(img, (x0, y_cap), (x1, y1_cap), (40, 255, 200), -1)
        cv2.line(img, (0, baseline), (width - 1, baseline), (35, 55, 45), 1)

    def _paint_classic(self, img, levels, width: int, height: int) -> None:
        import cv2

        n = len(levels)
        usable_h, gap, bar_w, baseline = self._bar_geom(n, width, height)
        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            h = int(v * usable_h)
            x0 = gap + i * (bar_w + gap)
            x1 = min(width - 1, x0 + bar_w)
            if h < 1 or x1 <= x0:
                continue
            color = (0, int(180 + 75 * v), int(120 + 100 * v))
            cv2.rectangle(img, (x0, baseline - h), (x1, baseline), color, -1)
        cv2.line(img, (0, baseline), (width - 1, baseline), (40, 40, 40), 1)

    def _paint_mirror(self, img, levels, width: int, height: int) -> None:
        import cv2

        n = len(levels)
        mid = height // 2
        half = max(1, mid - 2)
        gap = 1
        bar_w = max(1, (width - gap * (n + 1)) // n)
        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            h = int(v * half)
            x0 = gap + i * (bar_w + gap)
            x1 = min(width - 1, x0 + bar_w)
            if h < 1 or x1 <= x0:
                continue
            upper = (0, int(150 + 100 * v), int(90 + 130 * v))
            lower = (0, int(80 + 70 * v), int(50 + 80 * v))
            cv2.rectangle(img, (x0, mid - h), (x1, mid), upper, -1)
            cv2.rectangle(img, (x0, mid), (x1, mid + h), lower, -1)
        cv2.line(img, (0, mid), (width - 1, mid), (45, 70, 55), 1)

    def _paint_heat(self, img, levels, peaks, width: int, height: int) -> None:
        """Green bars with magenta tips (DrakeVox accent) on loud bins."""
        import cv2

        n = len(levels)
        usable_h, gap, bar_w, baseline = self._bar_geom(n, width, height)
        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            p = float(max(0.0, min(1.0, peaks[i] if i < len(peaks) else v)))
            h_live = int(v * usable_h)
            h_peak = int(p * usable_h)
            x0 = gap + i * (bar_w + gap)
            x1 = min(width - 1, x0 + bar_w)
            if x1 <= x0:
                continue
            if h_peak > h_live and h_peak > 0:
                trail = (20, int(30 + 40 * p), int(40 + 80 * p))
                cv2.rectangle(
                    img, (x0, baseline - h_peak), (x1, baseline), trail, -1
                )
            if h_live > 0:
                # Split bar: green body, magenta tip on top third when hot
                tip_h = max(1, int(h_live * 0.28)) if v > 0.45 else 0
                body_h = h_live - tip_h
                if body_h > 0:
                    green = (0, int(140 + 100 * v), int(90 + 100 * v))
                    cv2.rectangle(
                        img,
                        (x0, baseline - body_h),
                        (x1, baseline),
                        green,
                        -1,
                    )
                if tip_h > 0:
                    # BGR magenta / pink
                    mag = (int(180 + 75 * v), int(30 + 40 * v), int(200 + 55 * v))
                    cv2.rectangle(
                        img,
                        (x0, baseline - h_live),
                        (x1, baseline - body_h),
                        mag,
                        -1,
                    )
        cv2.line(img, (0, baseline), (width - 1, baseline), (35, 45, 50), 1)

    def _paint_bands(self, img, levels, width: int, height: int) -> None:
        """Low→mid→high color ramp across bar index."""
        import cv2

        n = len(levels)
        usable_h, gap, bar_w, baseline = self._bar_geom(n, width, height)
        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            h = int(v * usable_h)
            x0 = gap + i * (bar_w + gap)
            x1 = min(width - 1, x0 + bar_w)
            if h < 1 or x1 <= x0:
                continue
            t = i / max(1, n - 1)  # 0 low … 1 high
            # BGR: teal lows → green mids → cyan highs
            b = int(40 + 120 * t + 40 * v)
            g = int(140 + 90 * v)
            r = int(60 + 40 * (1.0 - t) + 50 * v)
            cv2.rectangle(
                img,
                (x0, baseline - h),
                (x1, baseline),
                (min(255, b), min(255, g), min(255, r)),
                -1,
            )
        cv2.line(img, (0, baseline), (width - 1, baseline), (35, 50, 45), 1)

    def _paint_grid(self, img, levels, peaks, width: int, height: int) -> None:
        """Phosphor bars + faint horizontal reticle."""
        import cv2

        # Grid first so bars sit on top
        for frac in (0.25, 0.5, 0.75):
            y = int(height * (1.0 - frac * 0.85) - 2)
            cv2.line(img, (0, y), (width - 1, y), (22, 38, 30), 1)
        self._paint_phosphor(img, levels, peaks, width, height)

    def _paint_wave(self, img, levels, width: int, height: int) -> None:
        """Oscilloscope-style polyline through FFT bar tops (not time-domain)."""
        import cv2

        n = len(levels)
        usable_h, gap, bar_w, baseline = self._bar_geom(n, width, height)
        pts = []
        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            x = gap + i * (bar_w + gap) + bar_w // 2
            y = baseline - int(v * usable_h)
            pts.append((x, y))
        if len(pts) >= 2:
            arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
            # Dim fill under curve
            fill = arr.copy()
            bottom = np.array(
                [[[pts[-1][0], baseline]], [[pts[0][0], baseline]]],
                dtype=np.int32,
            )
            poly = np.vstack([fill, bottom])
            overlay = img.copy()
            cv2.fillPoly(overlay, [poly], (0, 50, 35))
            cv2.addWeighted(overlay, 0.45, img, 0.55, 0, img)
            cv2.polylines(img, [arr], False, (0, 230, 160), 2, cv2.LINE_AA)
            # Bright dots at samples
            for x, y in pts[:: max(1, n // 16)]:
                cv2.circle(img, (x, y), 2, (40, 255, 200), -1, cv2.LINE_AA)
        cv2.line(img, (0, baseline), (width - 1, baseline), (35, 55, 45), 1)

    def _paint_win98(self, img, samples, width: int, height: int) -> None:
        """Windows 98 / classic Media Player style time-domain waveform.

        Uses raw PCM amplitude (not FFT). Dark navy panel, lime green trace,
        mid-line — cheap at strip size.
        """
        import cv2

        # Classic player look: near-black navy (BGR)
        img[:] = (32, 16, 0)
        mid = max(1, height // 2)
        # Faint grid (optional period feel)
        for frac in (0.25, 0.5, 0.75):
            y = int(height * frac)
            cv2.line(img, (0, y), (width - 1, y), (48, 28, 8), 1)
        for x in range(0, width, max(24, width // 8)):
            cv2.line(img, (x, 0), (x, height - 1), (40, 22, 6), 1)
        # Center zero line
        cv2.line(img, (0, mid), (width - 1, mid), (90, 90, 40), 1)

        if samples is None or getattr(samples, "size", 0) < 4:
            return
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        # Soft peak normalize so quiet mics still move; clip hard spikes
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak > 1e-5:
            x = np.clip(x / peak, -1.0, 1.0)
        else:
            x = x * 0.0
        # One y-sample per pixel column (decimate)
        n = int(x.size)
        xs = np.linspace(0, n - 1, num=max(2, width), dtype=np.float32)
        idx = np.clip(xs.astype(np.int32), 0, n - 1)
        ys = x[idx]
        amp = max(2, mid - 2)
        pts = np.zeros((width, 1, 2), dtype=np.int32)
        for i in range(width):
            pts[i, 0, 0] = i
            pts[i, 0, 1] = int(np.clip(mid - ys[i] * amp, 0, height - 1))
        # Soft under-glow then bright core (WMP-ish)
        cv2.polylines(img, [pts], False, (0, 120, 40), 3, cv2.LINE_AA)
        cv2.polylines(img, [pts], False, (40, 255, 80), 1, cv2.LINE_AA)

    def _paint_glow(self, img, levels, peaks, width: int, height: int) -> None:
        """Soft neon bloom under sharp bars (blur on a tiny buffer — cheap)."""
        import cv2

        glow = np.zeros_like(img)
        self._paint_phosphor(glow, levels, peaks, width, height)
        # Small ksize is enough at ~56px height
        k = 9 if height >= 40 else 5
        if k % 2 == 0:
            k += 1
        blurred = cv2.GaussianBlur(glow, (k, k), 0)
        cv2.addWeighted(blurred, 0.75, img, 1.0, 0, img)
        # Sharp core on top
        self._paint_phosphor(img, levels, peaks, width, height)

    def _paint_dots(self, img, levels, peaks, width: int, height: int) -> None:
        """LED-style dots at live level + dim peak ghost."""
        import cv2

        n = len(levels)
        usable_h, gap, bar_w, baseline = self._bar_geom(n, width, height)
        r = max(1, min(3, bar_w // 2))
        for i in range(n):
            v = float(max(0.0, min(1.0, levels[i])))
            p = float(max(0.0, min(1.0, peaks[i] if i < len(peaks) else v)))
            x = gap + i * (bar_w + gap) + bar_w // 2
            if p > 0.02:
                y_p = baseline - int(p * usable_h)
                cv2.circle(
                    img,
                    (x, y_p),
                    r,
                    (0, int(50 + 40 * p), int(40 + 30 * p)),
                    -1,
                    cv2.LINE_AA,
                )
            if v > 0.02:
                y_v = baseline - int(v * usable_h)
                cv2.circle(
                    img,
                    (x, y_v),
                    r + 1,
                    (0, int(180 + 75 * v), int(120 + 100 * v)),
                    -1,
                    cv2.LINE_AA,
                )
        cv2.line(img, (0, baseline), (width - 1, baseline), (35, 55, 45), 1)

    def _paint_waterfall(self, img, history, width: int, height: int) -> None:
        """Time-vs-frequency heat strip (bottom = newest).

        Cheap at strip size: resize a small float grid with INTER_NEAREST.
        Heavier than single-frame bars, still fine for ~48×64 history.
        """
        import cv2

        if history is None or getattr(history, "size", 0) == 0:
            return
        # history: rows × bars (oldest first)
        if history.ndim == 1:
            history = history.reshape(1, -1)
        rows, cols = history.shape
        # Color map: dark → SLS green → cyan tips
        h_f = np.clip(history.astype(np.float32), 0.0, 1.0)
        b = (40 + 180 * h_f).astype(np.uint8)
        g = (30 + 220 * h_f).astype(np.uint8)
        r = (20 + 80 * h_f * h_f).astype(np.uint8)
        small = np.dstack([b, g, r])
        # Flip so newest is at bottom of strip
        small = np.flipud(small)
        scaled = cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)
        np.copyto(img, scaled)
        # Thin top edge so HUD text stays readable
        cv2.rectangle(img, (0, 0), (width - 1, 14), (8, 12, 10), -1)

    def _draw_overlay(self, img, width: int, height: int) -> None:
        import cv2

        # Source / device name is Settings-only (mic_label) — do not burn into
        # the strip (live UI clutter; would also stamp Record if composite later).
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
