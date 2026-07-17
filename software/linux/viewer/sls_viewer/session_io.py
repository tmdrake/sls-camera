"""Session snapshot, recording (video + mic audio into AVI), anomaly log."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import cv2
import numpy as np

from .audio_device import pick_input_device
from .config import VIEWER_ROOT

if TYPE_CHECKING:
    from .spectrum import SpectrumAnalyzer

CAPTURES_DIR = VIEWER_ROOT / "captures"

# Mic capture defaults for recording (float32 → int16 WAV → mux into AVI).
# App does not set ALSA/Pulse gain — OS device level is used as-is (typically
# full capture / 100% on a fresh Pulse source). Spectrum only normalizes bars.
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1


def _find_ffmpeg() -> Optional[str]:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class SessionRecorder:
    def __init__(self, captures_dir: Path = CAPTURES_DIR):
        self.captures_dir = Path(captures_dir)
        self._lock = threading.Lock()
        self._writer: Optional[cv2.VideoWriter] = None
        self._path: Optional[Path] = None
        self._video_tmp: Optional[Path] = None
        self._audio_tmp: Optional[Path] = None
        self._recording = False
        self._fps = 15.0
        self._record_started: float = 0.0
        self._last_detected = 0
        self._session_log: Optional[Path] = None
        self._flash = ""
        self._flash_until = 0.0
        self._audio_chunks: List[np.ndarray] = []
        self._audio_stream = None
        self._audio_device_name = ""
        self._has_audio = False
        self._spectrum: Optional["SpectrumAnalyzer"] = None
        self._via_spectrum = False

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

    def _on_pcm(self, mono: np.ndarray) -> None:
        """PCM sink shared with SpectrumAnalyzer (float32 mono)."""
        try:
            with self._lock:
                if self._recording:
                    self._audio_chunks.append(mono.copy())
        except Exception:
            pass

    def _start_audio_own(self) -> bool:
        """Open a dedicated PortAudio input (when spectrum is not sharing)."""
        self._audio_chunks = []
        self._has_audio = False
        self._audio_device_name = ""
        self._via_spectrum = False
        try:
            import sounddevice as sd
        except Exception:
            return False

        device, label = pick_input_device(sd)
        self._audio_device_name = label or "default"

        def callback(indata, frames, time_info, status):
            try:
                mono = indata[:, 0].astype(np.float32)
                self._on_pcm(mono)
            except Exception:
                pass

        try:
            kwargs = dict(
                channels=AUDIO_CHANNELS,
                samplerate=AUDIO_SAMPLE_RATE,
                blocksize=1024,
                dtype="float32",
                callback=callback,
            )
            if device is not None:
                kwargs["device"] = device
            self._audio_stream = sd.InputStream(**kwargs)
            self._audio_stream.start()
            self._has_audio = True
            return True
        except Exception:
            self._audio_stream = None
            self._has_audio = False
            return False

    def _start_audio(
        self, spectrum: Optional["SpectrumAnalyzer"] = None
    ) -> bool:
        """Capture mic for mux. Prefer sharing spectrum stream (one device open)."""
        self._audio_chunks = []
        self._has_audio = False
        self._audio_device_name = ""
        self._via_spectrum = False
        self._spectrum = spectrum

        if spectrum is not None:
            # Piggyback on the spectrum PortAudio stream (one open of Kinect mic).
            spectrum.add_pcm_sink(self._on_pcm)
            if not spectrum.active:
                spectrum.ensure_running()
            if spectrum.active:
                self._via_spectrum = True
                self._has_audio = True
                self._audio_device_name = spectrum.device_name or "shared mic"
                return True
            # Stream failed to open — drop sink and try a dedicated open
            try:
                spectrum.remove_pcm_sink(self._on_pcm)
            except Exception:
                pass

        return self._start_audio_own()

    def _stop_audio_capture(self) -> None:
        if self._via_spectrum and self._spectrum is not None:
            try:
                self._spectrum.remove_pcm_sink(self._on_pcm)
            except Exception:
                pass
        self._via_spectrum = False
        self._spectrum = None
        if self._audio_stream is not None:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None

    def _write_wav(self, path: Path) -> bool:
        with self._lock:
            chunks = list(self._audio_chunks)
            self._audio_chunks = []
        if not chunks:
            return False
        audio = np.concatenate(chunks)
        pcm = np.clip(audio, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
        try:
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(AUDIO_SAMPLE_RATE)
                wf.writeframes(pcm.tobytes())
            return True
        except Exception:
            return False

    def _mux_av(self, video_path: Path, audio_path: Path, out_path: Path) -> bool:
        """Mux MJPG video + PCM WAV into a single AVI (audio inside the AVI)."""
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            return False
        # AVI + PCM is widely playable; copy MJPG video stream as-is.
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "pcm_s16le",
            "-shortest",
            str(out_path),
        ]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                check=False,
            )
            return (
                r.returncode == 0
                and out_path.is_file()
                and out_path.stat().st_size > 0
            )
        except Exception:
            return False

    def start_record(
        self,
        bgr: np.ndarray,
        fps: float = 15.0,
        spectrum: Optional["SpectrumAnalyzer"] = None,
    ) -> Optional[Path]:
        if self._recording:
            return self._path
        if bgr is None or bgr.size == 0:
            self._set_flash("record failed: no frame")
            return None
        self.ensure_dir()
        h, w = bgr.shape[:2]
        ts = self._ts()
        # video-only temp; final AVI gets audio muxed in when possible
        video_tmp = self.captures_dir / f"sls_{ts}_video.avi"
        audio_tmp = self.captures_dir / f"sls_{ts}_audio.wav"
        final = self.captures_dir / f"sls_{ts}.avi"

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(str(video_tmp), fourcc, float(fps), (w, h))
        if not writer.isOpened():
            self._set_flash("record failed: codec")
            return None

        audio_ok = self._start_audio(spectrum=spectrum)
        with self._lock:
            self._writer = writer
            self._video_tmp = video_tmp
            self._audio_tmp = audio_tmp
            self._path = final
            self._recording = True
            self._fps = float(fps)
            self._record_started = time.time()

        if audio_ok:
            self._set_flash(f"recording {final.name} +audio")
        else:
            self._set_flash(f"recording {video_tmp.name} (video only)")
        self._log_event(
            "record_start",
            {
                "file": final.name,
                "audio": audio_ok,
                "mic": self._audio_device_name,
            },
        )
        return final

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
        video_tmp = self._video_tmp
        audio_tmp = self._audio_tmp
        elapsed = self.recording_elapsed_str() if self._recording else "0:00"
        had_audio = self._has_audio

        with self._lock:
            if self._writer is not None:
                try:
                    self._writer.release()
                except Exception:
                    pass
            self._writer = None
            self._recording = False
            self._record_started = 0.0

        self._stop_audio_capture()

        final_path = path
        audio_saved = False
        muxed = False
        if had_audio and audio_tmp is not None:
            audio_saved = self._write_wav(audio_tmp)

        if (
            audio_saved
            and video_tmp is not None
            and path is not None
            and video_tmp.is_file()
        ):
            muxed = self._mux_av(video_tmp, audio_tmp, path)
            if muxed:
                for tmp in (video_tmp, audio_tmp):
                    try:
                        tmp.unlink(missing_ok=True)
                    except TypeError:
                        if tmp.exists():
                            tmp.unlink()
                final_path = path
                self._path = final_path
                self._set_flash(f"saved {final_path.name} +audio ({elapsed})")
            else:
                # Sidecar: keep video AVI + WAV when ffmpeg missing/fails
                final_path = video_tmp
                self._path = video_tmp
                self._set_flash(
                    f"saved {video_tmp.name} + {audio_tmp.name} ({elapsed})"
                    " — install ffmpeg or imageio-ffmpeg to mux"
                )
        elif video_tmp is not None and video_tmp.is_file():
            # Rename video-only temp to final name when no audio
            final_path = path if path is not None else video_tmp
            if path is not None and path != video_tmp:
                try:
                    video_tmp.rename(path)
                    final_path = path
                except OSError:
                    final_path = video_tmp
            self._path = final_path
            self._set_flash(f"saved {final_path.name} ({elapsed})")
        else:
            self._set_flash("record stop: no file")

        self._log_event(
            "record_stop",
            {
                "file": final_path.name if final_path else None,
                "elapsed": elapsed,
                "muxed": muxed,
                "audio": audio_saved,
            },
        )
        self._video_tmp = None
        self._audio_tmp = None
        self._has_audio = False
        return final_path

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

    def note_ovilus(self, word: str) -> None:
        self._log_event("ovilus", {"word": word})
        self._set_flash(f"OVILUS: {word}", seconds=4.0)

    def note_detection(
        self, detected: int, auto_snap: bool, bgr: Optional[np.ndarray]
    ) -> None:
        prev = self._last_detected
        cur = int(detected)
        if cur > 0 and prev == 0:
            self._log_event("detect_appear", {"detected": cur})
            if auto_snap and bgr is not None:
                self.snapshot(bgr)
        elif cur == 0 and prev > 0:
            self._log_event("detect_disappear", {"detected": 0})
        self._last_detected = cur
