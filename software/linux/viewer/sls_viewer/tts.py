"""Text-to-speech for DrakeVox words.

Synthesis order:
  1) espeak-ng / espeak CLI (-w WAV)
  2) libespeak-ng.so via ctypes (common when only libespeak-ng1 is installed)
  3) Live-only: espeak CLI / spd-say (no PCM for AVI)

PCM is mono float32 at DEFAULT_SAMPLE_RATE for mixing into AVI recordings.

Performance (field tablets): full ensure_max_output_volume() + espeak CLI on the
UI thread every speak is expensive on 2 GB Atom devices. Prefer once-per-session
mixer setup and async synth/play — track sls-camera#13.

CPU priority (#13/#14): speak worker tries nice/setpriority; pauses MediaPipe via
busy callback so synth/play are not starved under freenect+pose load.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

DEFAULT_SAMPLE_RATE = 16000

# espeak_AUDIO_OUTPUT
_AUDIO_OUTPUT_PLAYBACK = 0
_AUDIO_OUTPUT_RETRIEVAL = 1
_AUDIO_OUTPUT_SYNCHRONOUS = 2
_AUDIO_OUTPUT_SYNCH_PLAYBACK = 3

_ESPEAK_CHARS_AUTO = 0
_ESPEAK_SSML = 0x10


def find_espeak_cli() -> Optional[str]:
    for name in ("espeak-ng", "espeak"):
        p = shutil.which(name)
        if p:
            return p
    return None


def backend_name() -> str:
    if find_espeak_cli():
        return find_espeak_cli() or "espeak-cli"
    try:
        ctypes.CDLL("libespeak-ng.so.1")
        return "libespeak-ng"
    except OSError:
        pass
    try:
        ctypes.CDLL("libespeak.so.1")
        return "libespeak"
    except OSError:
        pass
    if shutil.which("spd-say"):
        return "spd-say (live only)"
    return "none"


def _resample_mono(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if src_sr <= 0 or dst_sr <= 0 or x.size == 0 or src_sr == dst_sr:
        return x.astype(np.float32, copy=False)
    n = max(1, int(round(x.size * float(dst_sr) / float(src_sr))))
    xp = np.linspace(0.0, 1.0, num=x.size, endpoint=False)
    xq = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(xq, xp, x).astype(np.float32)


def _read_wav_mono_f32(path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = int(wf.getframerate())
        raw = wf.readframes(wf.getnframes())
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 1:
        pcm = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if nch > 1:
        pcm = pcm.reshape(-1, nch).mean(axis=1)
    return pcm.astype(np.float32), sr


def _synthesize_cli(text: str, rate_wpm: int) -> Optional[Tuple[np.ndarray, int]]:
    eng = find_espeak_cli()
    if not eng:
        return None
    tmp: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = Path(f.name)
        r = subprocess.run(
            [eng, "-w", str(tmp), "-s", str(int(rate_wpm)), "-v", "en", text],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if r.returncode != 0 or tmp is None or not tmp.is_file() or tmp.stat().st_size < 44:
            return None
        return _read_wav_mono_f32(tmp)
    except Exception:
        return None
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except TypeError:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass


_lib_lock = threading.Lock()
_lib = None
_lib_sr = 22050
_lib_ok = False


def _load_espeak_lib():
    global _lib, _lib_sr, _lib_ok
    if _lib_ok:
        return _lib
    with _lib_lock:
        if _lib_ok:
            return _lib
        for name in ("libespeak-ng.so.1", "libespeak-ng.so", "libespeak.so.1", "libespeak.so"):
            try:
                lib = ctypes.CDLL(name)
            except OSError:
                continue
            try:
                lib.espeak_Initialize.argtypes = [
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                ]
                lib.espeak_Initialize.restype = ctypes.c_int
                lib.espeak_SetSynthCallback.argtypes = [ctypes.c_void_p]
                lib.espeak_SetSynthCallback.restype = None
                lib.espeak_Synth.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_size_t,
                    ctypes.c_uint,
                    ctypes.c_int,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.POINTER(ctypes.c_uint),
                    ctypes.c_void_p,
                ]
                lib.espeak_Synth.restype = ctypes.c_int
                lib.espeak_Synchronize.argtypes = []
                lib.espeak_Synchronize.restype = ctypes.c_int
                try:
                    lib.espeak_SetParameter.argtypes = [
                        ctypes.c_int,
                        ctypes.c_int,
                        ctypes.c_int,
                    ]
                    lib.espeak_SetParameter.restype = ctypes.c_int
                except Exception:
                    pass
                # buflength 0 = default; path None = default data
                sr = lib.espeak_Initialize(
                    _AUDIO_OUTPUT_RETRIEVAL, 0, None, 0
                )
                if sr <= 0:
                    # some builds return 0 on failure with different semantics
                    continue
                _lib = lib
                _lib_sr = int(sr)
                _lib_ok = True
                return _lib
            except Exception:
                continue
        _lib = None
        _lib_ok = False
        return None


# Callback type: int callback(short *wav, int numsamples, espeak_EVENT *events)
_CB_TYPE = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_short),
    ctypes.c_int,
    ctypes.c_void_p,
)


def _synthesize_lib(text: str, rate_wpm: int) -> Optional[Tuple[np.ndarray, int]]:
    lib = _load_espeak_lib()
    if lib is None:
        return None
    chunks: List[np.ndarray] = []

    def _cb(wav_ptr, numsamples, events):
        if wav_ptr and numsamples > 0:
            buf = ctypes.cast(
                wav_ptr, ctypes.POINTER(ctypes.c_short * numsamples)
            ).contents
            arr = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
            chunks.append(arr.copy())
        return 0  # continue

    cb = _CB_TYPE(_cb)
    try:
        with _lib_lock:
            lib.espeak_SetSynthCallback(cb)
            # espeak RATE parameter id is 1
            try:
                lib.espeak_SetParameter(1, int(rate_wpm), 0)
            except Exception:
                pass
            data = text.encode("utf-8") + b"\0"
            uid = ctypes.c_uint(0)
            rc = lib.espeak_Synth(
                data,
                len(data),
                0,
                0,  # POS_CHARACTER
                0,
                _ESPEAK_CHARS_AUTO,
                ctypes.byref(uid),
                None,
            )
            if rc != 0:
                return None
            lib.espeak_Synchronize()
        if not chunks:
            return None
        pcm = np.concatenate(chunks).astype(np.float32)
        return pcm, int(_lib_sr)
    except Exception:
        return None


def synthesize(
    text: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    rate_wpm: int = 140,
) -> Optional[np.ndarray]:
    """Mono float32 PCM in [-1, 1] at sample_rate, or None.

    Prefer in-process libespeak (no process spawn) then CLI WAV (#13).
    """
    word = (text or "").strip()
    if not word:
        return None
    got = _synthesize_lib(word, rate_wpm)
    if got is None:
        got = _synthesize_cli(word, rate_wpm)
    if got is None:
        return None
    pcm, sr = got
    return _resample_mono(pcm, int(sr), int(sample_rate))


# Once-per-session mixer setup — full amixer/wpctl every word is slow on Atom (#13)
_volume_ready = False
_volume_lock = threading.Lock()


def ensure_max_output_volume(*, force: bool = False) -> None:
    """Unmute + raise system playback (once per session unless force=True).

    Field tablets often leave PipeWire/ALSA muted or low after idle.
    Best-effort; silent if tools missing. Does not fix Dummy Output —
    firmware sls-audio-speakers handles RCA panel path at boot.
    """
    global _volume_ready
    with _volume_lock:
        if _volume_ready and not force:
            return
        _ensure_max_output_volume_impl()
        _volume_ready = True


def _ensure_max_output_volume_impl() -> None:
    # PipeWire (Lubuntu default)
    wp = shutil.which("wpctl")
    if wp:
        for args in (
            [wp, "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
            [wp, "set-volume", "@DEFAULT_AUDIO_SINK@", "1.0"],
            # Some builds accept percent form
            [wp, "set-volume", "@DEFAULT_AUDIO_SINK@", "100%"],
        ):
            try:
                subprocess.run(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass
    # PulseAudio-compatible (PipeWire pulse shim)
    pactl = shutil.which("pactl")
    if pactl:
        for args in (
            [pactl, "set-sink-mute", "@DEFAULT_SINK@", "0"],
            [pactl, "set-sink-volume", "@DEFAULT_SINK@", "100%"],
        ):
            try:
                subprocess.run(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass
    # ALSA Master / PCM (when present)
    amixer = shutil.which("amixer")
    if amixer:
        for ctl in ("Master", "PCM", "Speaker", "Headphone"):
            try:
                subprocess.run(
                    [amixer, "-q", "sset", ctl, "100%", "unmute"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass
        # Cherry Trail RT5651 (RCA): false "Headphone Jack" sense keeps UCM on
        # Headphones and mutes Speaker. Force UCM Speaker enable sequence on
        # any card that has a Speaker Switch (bytcr-rt5651 is usually card 1).
        for card in ("0", "1", "2"):
            try:
                r = subprocess.run(
                    [amixer, "-c", card, "sget", "Speaker"],
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
                if r.returncode != 0:
                    continue
            except Exception:
                continue
            for name, val in (
                ("Speaker Switch", "on"),
                ("LOUT L Playback Switch", "on"),
                ("LOUT R Playback Switch", "on"),
                ("LOUT MIX DAC L1 Switch", "on"),
                ("LOUT MIX DAC R1 Switch", "on"),
                # Keep HP path on: PipeWire default sink is often "Headphones";
                # forcing HPO off silences DrakeVox even with Speaker on.
                ("Headphone Switch", "on"),
                ("HPO L Playback Switch", "on"),
                ("HPO R Playback Switch", "on"),
                # RCA: UCM often leaves OUT at 0 → silent
                ("OUT Playback Volume", "39"),
            ):
                try:
                    subprocess.run(
                        [amixer, "-c", card, "-q", "cset", f"name={name}", val],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=2,
                        check=False,
                    )
                except Exception:
                    pass
            try:
                subprocess.run(
                    [amixer, "-c", card, "-q", "sset", "Speaker", "on"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass
            try:
                subprocess.run(
                    [amixer, "-c", card, "-q", "sset", "Headphone", "100%", "unmute"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass
            break


def _boost_current_thread_priority() -> str:
    """Best-effort raise scheduling priority for the TTS worker.

    Negative nice usually needs CAP_SYS_NICE / root; still try. Returns a short
    tag for debugging (nice / setpriority / none).
    """
    tags: List[str] = []
    for delta in (-10, -5):
        try:
            os.nice(int(delta))
            tags.append(f"nice{delta}")
            break
        except (OSError, AttributeError, PermissionError):
            continue
    try:
        # PRIO_PROCESS=0, who=0 (this thread/process on Linux)
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        if hasattr(libc, "setpriority"):
            for prio in (-10, -5):
                rc = int(libc.setpriority(0, 0, int(prio)))
                if rc == 0:
                    tags.append(f"setpriority{prio}")
                    break
    except Exception:
        pass
    return "+".join(tags) if tags else "none"


def play_pcm(
    pcm: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    *,
    ensure_volume: bool = False,
    wait: bool = False,
) -> bool:
    try:
        import sounddevice as sd
    except Exception:
        return False
    try:
        if ensure_volume:
            ensure_max_output_volume()
        # Peak-normalize soft espeak so panel speakers aren't tiny at 100%
        x = np.asarray(pcm, dtype=np.float32).reshape(-1)
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak > 1e-6 and peak < 0.85:
            x = np.clip(x * (0.95 / peak), -1.0, 1.0)
        # wait=True: hold CPU preference through playback (pose stays paused)
        sd.play(x, samplerate=int(sample_rate), blocking=bool(wait))
        return True
    except Exception:
        return False


def play_live_fallback(text: str, *, ensure_volume: bool = False) -> bool:
    word = (text or "").strip()
    if not word:
        return False
    if ensure_volume:
        ensure_max_output_volume()
    eng = find_espeak_cli()
    if eng:
        try:
            # -a amplitude 0–200; max for field audibility
            subprocess.Popen(
                [eng, "-s", "140", "-a", "200", "-v", "en", word],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass
    spd = shutil.which("spd-say")
    if spd:
        try:
            subprocess.Popen(
                [spd, word],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass
    return False


class DrakeVoxTTS:
    """Synthesize + speak DrakeVox words; PCM callback for AVI mix.

    Latency notes (#13): mixer setup once; libespeak preferred; speak() runs
    synth+play on a worker so the Qt UI thread is not blocked.

    CPU (#13/#14): busy-callback pauses MediaPipe during synth+play; worker
    tries nice/setpriority; playback waits so pose stays off until audio ends.

    Recording safety: AVI inject uses wall-time captured at queue time and an
    optional ``record_gen`` so a late worker cannot paste into the next REC.
    Call :meth:`flush` before ``stop_record`` so in-flight words still mux.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE):
        self.sample_rate = int(sample_rate)
        self._lock = threading.Lock()
        # cb(pcm, wall_time) or cb(pcm, wall_time, record_gen=…)
        self._on_pcm: Optional[Callable[..., None]] = None
        # cb(busy: bool) — True while synth+play holds CPU preference
        self._on_busy: Optional[Callable[[bool], None]] = None
        self._last_error = ""
        self._worker: Optional[threading.Thread] = None
        self._warmed = False

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def can_synthesize(self) -> bool:
        return synthesize("test", sample_rate=self.sample_rate) is not None

    def set_record_callback(
        self, cb: Optional[Callable[..., None]]
    ) -> None:
        with self._lock:
            self._on_pcm = cb

    def set_busy_callback(self, cb: Optional[Callable[[bool], None]]) -> None:
        """Notify host when TTS is using the CPU (pause pose, etc.)."""
        with self._lock:
            self._on_busy = cb

    def _emit_busy(self, busy: bool) -> None:
        with self._lock:
            cb = self._on_busy
        if cb is None:
            return
        try:
            cb(bool(busy))
        except Exception:
            pass

    def warm(self) -> None:
        """Once at app start: mixer + load espeak (background, non-blocking)."""
        if self._warmed:
            return
        self._warmed = True

        def _job() -> None:
            try:
                _boost_current_thread_priority()
                ensure_max_output_volume(force=True)
                # Preload lib / first-synth cost off the first DrakeVox trigger
                synthesize("ok", sample_rate=self.sample_rate)
            except Exception:
                pass

        threading.Thread(target=_job, name="tts-warm", daemon=True).start()

    def flush(self, timeout: float = 2.5) -> None:
        """Wait for in-flight speak worker (inject + play) before stop REC."""
        with self._lock:
            prev = self._worker
        if prev is not None and prev.is_alive():
            # Play can block ~1–2s per word; allow enough time
            prev.join(timeout=max(0.0, float(timeout)))

    def speak(
        self,
        text: str,
        *,
        when: Optional[float] = None,
        record_gen: Optional[int] = None,
    ) -> Tuple[bool, Optional[np.ndarray]]:
        """Queue word for synth+play off the UI thread. Returns immediately.

        PCM for AVI is injected from the worker when ready. ``when`` (epoch) is
        the mix offset anchor — default is **queue time**, not post-synth, so
        AVI placement matches when the operator heard the word trigger.
        ``record_gen`` ties the clip to one SessionRecorder take.
        """
        import time as _time

        word = (text or "").strip()
        if not word:
            return False, None

        # Capture before worker so long synth does not slide the AVI offset
        t0 = float(when if when is not None else _time.time())
        gen = record_gen

        with self._lock:
            prev = self._worker

        def _job() -> None:
            # Serialize on the worker (not UI): wait for prior inject+play
            if prev is not None and prev.is_alive():
                prev.join(timeout=5.0)
            self._emit_busy(True)
            try:
                prio = _boost_current_thread_priority()
                # First word (or cold start): ensure volume once; cheap no-op after
                ensure_max_output_volume(force=False)
                pcm = synthesize(word, sample_rate=self.sample_rate)
                if pcm is not None and pcm.size > 0:
                    with self._lock:
                        cb = self._on_pcm
                    if cb is not None:
                        try:
                            if gen is not None:
                                cb(pcm, t0, record_gen=gen)
                            else:
                                cb(pcm, t0)
                        except TypeError:
                            # Older callback without record_gen kw
                            try:
                                cb(pcm, t0)
                            except Exception:
                                pass
                        except Exception:
                            pass
                    # Live speakers — wait so pose stays paused through playback
                    if not play_pcm(
                        pcm, self.sample_rate, ensure_volume=False, wait=True
                    ):
                        ensure_max_output_volume(force=True)
                        if not play_pcm(
                            pcm, self.sample_rate, ensure_volume=False, wait=True
                        ):
                            play_live_fallback(word, ensure_volume=False)
                            # CLI fallback is async; brief hold still helps
                            _time.sleep(min(2.0, 0.4 + 0.08 * len(word)))
                    self._last_error = ""
                    if prio != "none":
                        # One-shot debug (quiet unless useful on Atom)
                        pass
                    return
                self._last_error = "TTS synth unavailable (install espeak-ng)"
                # Live-only fallback: no PCM → nothing to inject (recording keeps mic)
                play_live_fallback(word, ensure_volume=True)
                _time.sleep(min(2.0, 0.4 + 0.08 * len(word)))
            except Exception as exc:
                self._last_error = str(exc)[:120]
            finally:
                self._emit_busy(False)

        t = threading.Thread(target=_job, name="tts-speak", daemon=True)
        with self._lock:
            self._worker = t
        t.start()
        return True, None
