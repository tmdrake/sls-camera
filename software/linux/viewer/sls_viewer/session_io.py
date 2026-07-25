"""Session snapshot, recording (video + mic audio into AVI), anomaly log."""

from __future__ import annotations

import json
import os
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
from .remedia import (
    ensure_captures_on_volume,
    list_removable_volumes,
    pick_auto_volume,
    resolve_captures_dir,
    copy_local_to_media,
)

if TYPE_CHECKING:
    from .spectrum import SpectrumAnalyzer

CAPTURES_DIR = VIEWER_ROOT / "captures"

# Mic capture defaults for recording (float32 → int16 WAV → mux into AVI).
# App does not set ALSA/Pulse gain — OS device level is used as-is (typically
# full capture / 100% on a fresh Pulse source). Spectrum only normalizes bars.
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1


def default_local_captures_dir() -> Path:
    """Local snaps/records dir; honor SLS_CAPTURES_DIR (firmware permanent media)."""
    env = (os.environ.get("SLS_CAPTURES_DIR") or "").strip()
    if env:
        return Path(env)
    return CAPTURES_DIR


def _find_ffmpeg() -> Optional[str]:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _ffmpeg_has_encoder(ffmpeg: str, name: str) -> bool:
    try:
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            timeout=8,
            check=False,
        )
        blob = (r.stdout or b"") + (r.stderr or b"")
        return name.encode("ascii", errors="ignore") in blob
    except Exception:
        return False


def _vaapi_render_device() -> Optional[str]:
    """First plausible VAAPI render node, or None."""
    for p in (
        "/dev/dri/renderD128",
        "/dev/dri/renderD129",
        "/dev/dri/renderD130",
    ):
        if os.path.exists(p):
            return p
    return None


def probe_h264_encoder(*, prefer_hardware: bool = True) -> str:
    """Return ``vaapi`` | ``libx264`` | ``none`` (session-level probe helper)."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return "none"
    if prefer_hardware and _vaapi_render_device() and _ffmpeg_has_encoder(
        ffmpeg, "h264_vaapi"
    ):
        return "vaapi"
    if _ffmpeg_has_encoder(ffmpeg, "libx264"):
        return "libx264"
    # VAAPI without prefer_hardware still useful if nothing else
    if _vaapi_render_device() and _ffmpeg_has_encoder(ffmpeg, "h264_vaapi"):
        return "vaapi"
    return "none"


class SessionRecorder:
    def __init__(self, captures_dir: Optional[Path] = None):
        if captures_dir is None:
            captures_dir = default_local_captures_dir()
        self._local_captures_dir = Path(captures_dir)
        self.captures_dir = Path(captures_dir)
        self._captures_label = "local"
        self._captures_target = "local"
        self._lock = threading.Lock()
        self._writer: Optional[cv2.VideoWriter] = None
        self._path: Optional[Path] = None
        self._video_tmp: Optional[Path] = None
        self._audio_tmp: Optional[Path] = None
        self._recording = False
        self._fps = 15.0  # nominal OpenCV stamp (field-lite 7.5)
        self._frame_count: int = 0  # frames written this take (wall-sync)
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
        # DrakeVox TTS clips: (offset_seconds from record start, float32 mono)
        self._tts_clips: List[tuple] = []
        # Bumps each start_record so async TTS from a prior take is dropped
        self._record_gen: int = 0
        # "avi" | "mp4" for current take; encoder cache for MP4 (#20)
        self._record_format: str = "avi"
        self._prefer_hw_encode: bool = False
        self._h264_encoder: Optional[str] = None  # vaapi|libx264|none

    @property
    def captures_label(self) -> str:
        return self._captures_label

    @property
    def record_generation(self) -> int:
        """Monotonic id of the current/last recording take (for async TTS)."""
        return int(self._record_gen)

    def set_captures_target(self, mode: str) -> str:
        """local | auto — resolve path (USB/SD when auto and media present)."""
        mode = "auto" if (mode or "").lower().strip() == "auto" else "local"
        self._captures_target = mode
        # Don't switch mid-record
        if self._recording:
            return self._captures_label
        path, label = resolve_captures_dir(mode, self._local_captures_dir)
        with self._lock:
            if path != self.captures_dir:
                # New session log location when dir changes
                self._session_log = None
            self.captures_dir = path
            self._captures_label = label
        return label

    def refresh_captures_dir(self) -> str:
        """Re-resolve auto target (media plugged/unplugged). No-op mid-record."""
        return self.set_captures_target(self._captures_target)

    def has_removable_media(self) -> bool:
        return pick_auto_volume() is not None

    def copy_local_captures_to_media(
        self, progress_cb=None
    ) -> tuple[int, int, str]:
        """
        Copy viewer/captures files onto current removable media (sls-captures/).

        Returns (copied, skipped, label). Does not delete local copies.
        progress_cb forwarded to remedia.copy_local_to_media (#18).
        """
        if self._recording:
            self._set_flash("stop recording before copy to media")
            return 0, 0, ""
        vol = pick_auto_volume()
        if vol is None:
            self._set_flash("no USB/SD media mounted")
            return 0, 0, ""
        dest = ensure_captures_on_volume(vol)
        if dest is None:
            self._set_flash("media not writable")
            return 0, 0, vol.short_label()
        copied, skipped = copy_local_to_media(
            self._local_captures_dir, dest, progress_cb=progress_cb
        )
        label = vol.short_label()
        if copied or skipped:
            self._set_flash(
                f"copied {copied} to media ({skipped} already there)"
            )
            self._log_event(
                "copy_local_to_media",
                {"copied": copied, "skipped": skipped, "dest": str(dest)},
            )
        else:
            self._set_flash("local captures empty — nothing to copy")
        # Prefer media for new captures after a successful copy path
        if self._captures_target == "auto":
            self.refresh_captures_dir()
        return copied, skipped, label

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

    def clear_captures(self) -> int:
        """Delete media/logs under captures dir. Returns number of files removed."""
        d = self.ensure_dir()
        n = 0
        try:
            for path in sorted(d.iterdir()):
                if not path.is_file():
                    continue
                try:
                    path.unlink()
                    n += 1
                except OSError:
                    pass
        except OSError:
            pass
        if n:
            self._set_flash(f"cleared {n} capture file(s)")
            self._log_event("clear_captures", {"count": n})
        else:
            self._set_flash("captures already empty")
        return n

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
                    # Real capture only — do not claim audio at stream-open alone
                    self._has_audio = True
                    self._pcm_samples = int(
                        getattr(self, "_pcm_samples", 0)
                    ) + int(np.asarray(mono).size)
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
            # Stream open; has_audio flips on first callback
            return True
        except Exception:
            self._audio_stream = None
            self._has_audio = False
            return False

    def inject_tts(
        self,
        pcm: np.ndarray,
        wall_time: float,
        record_gen: Optional[int] = None,
    ) -> None:
        """Queue TTS PCM to mix into the recording at wall_time (epoch).

        Safe with async DrakeVox (#13): drops clips that belong to another take
        (stale worker after Stop/Start) or that started before this recording.
        ``record_gen`` should be :attr:`record_generation` captured at speak().
        """
        if not self._recording or pcm is None:
            return
        try:
            arr = np.asarray(pcm, dtype=np.float32).reshape(-1)
        except Exception:
            return
        if arr.size == 0:
            return
        with self._lock:
            if not self._recording or self._record_started <= 0:
                return
            if record_gen is not None and int(record_gen) != int(self._record_gen):
                return
            offset = float(wall_time) - float(self._record_started)
            # Negative offset ⇒ speak was queued before this take (or clock skew).
            # Do NOT clamp to 0 — that used to paste stale TTS at t=0 of the next REC.
            if offset < -0.05:
                return
            offset = max(0.0, offset)
            self._tts_clips.append((offset, arr.copy()))
            self._has_audio = True
            n_clips = len(self._tts_clips)
        # Outside lock: best-effort session log for field QA (#23)
        try:
            self._log_event(
                "tts_inject",
                {
                    "offset_s": round(offset, 3),
                    "samples": int(arr.size),
                    "clips": n_clips,
                    "gen": int(record_gen) if record_gen is not None else None,
                },
            )
        except Exception:
            pass

    def _start_audio(
        self, spectrum: Optional["SpectrumAnalyzer"] = None
    ) -> bool:
        """Capture mic for mux. Prefer sharing spectrum stream (one device open).

        Note: do **not** set ``_has_audio`` until the first PCM callback (or TTS
        inject). Field-lite used to mark audio ready when the spectrum handle was
        open even if no samples ever arrived → silent AVI with no +audio mix.
        """
        self._audio_chunks = []
        self._tts_clips = []
        self._has_audio = False
        self._pcm_samples = 0
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
                # Capture arm only — has_audio set on first _on_pcm / inject_tts
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

    def _mix_audio(self) -> Optional[np.ndarray]:
        """Mic chunks + DrakeVox TTS clips → mono float32 timeline."""
        with self._lock:
            chunks = list(self._audio_chunks)
            clips = list(self._tts_clips)
            self._audio_chunks = []
            self._tts_clips = []
            elapsed = 0.0
            if self._record_started > 0:
                elapsed = max(0.0, time.time() - self._record_started)

        mic = np.concatenate(chunks).astype(np.float32) if chunks else None
        if mic is None and not clips:
            return None

        # Timeline length: mic length or enough for TTS + short pad
        n_mic = int(mic.size) if mic is not None else 0
        n_end = n_mic
        for offset_s, tts in clips:
            end = int(offset_s * AUDIO_SAMPLE_RATE) + int(tts.size)
            if end > n_end:
                n_end = end
        if elapsed > 0:
            n_end = max(n_end, int(elapsed * AUDIO_SAMPLE_RATE))
        n_end = max(n_end, 1)

        out = np.zeros(n_end, dtype=np.float32)
        if mic is not None and n_mic > 0:
            out[: min(n_mic, n_end)] = mic[: min(n_mic, n_end)]

        # Mix TTS louder than ambient so words stay clear on playback
        for offset_s, tts in clips:
            start = int(max(0.0, offset_s) * AUDIO_SAMPLE_RATE)
            if start >= n_end:
                continue
            seg = np.asarray(tts, dtype=np.float32).reshape(-1) * 0.95
            end = min(n_end, start + seg.size)
            n = end - start
            if n <= 0:
                continue
            out[start:end] += seg[:n]

        # Soft clip
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 1.0:
            out = out / peak
        return out

    def _write_wav(self, path: Path) -> bool:
        audio = self._mix_audio()
        if audio is None or audio.size == 0:
            return False
        # Near-silent mix (all zeros) is not useful — treat as no audio
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak < 1e-5:
            return False
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

    def _wall_video_fps(self, wall_s: float, n_frames: int) -> float:
        """FPS so n_frames span wall_s (video timeline = audio/DrakeVox).

        Field-lite labels OpenCV at 7.5 but Atom often writes slower; players
        then run video too fast vs wall-clock mic/TTS.
        """
        if n_frames >= 1 and wall_s > 0.05:
            return max(1.0, min(60.0, float(n_frames) / float(wall_s)))
        return max(1.0, float(self._fps or 15.0))

    def _pts_scale_for_wall(self, wall_s: float, n_frames: int) -> float:
        """PTS multiplier so nominal-fps content spans wall_s."""
        nom = max(0.1, float(self._fps or 7.5))
        if n_frames >= 1 and wall_s > 0.05:
            return max(0.25, min(4.0, (wall_s * nom) / float(n_frames)))
        return 1.0

    def _mux_av(
        self,
        video_path: Path,
        audio_path: Path,
        out_path: Path,
        *,
        wall_s: float = 0.0,
        n_frames: int = 0,
    ) -> bool:
        """Mux MJPG video + PCM WAV into a single AVI.

        Audio + DrakeVox are wall-clock. OpenCV stamps at nominal record_fps
        (field-lite **7.5**). If fewer frames than wall×7.5 were written, naive
        mux plays video too fast → mic/TTS feel early. Retime video to wall.
        """
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            return False

        true_fps = self._wall_video_fps(wall_s, n_frames)
        pts_scale = self._pts_scale_for_wall(wall_s, n_frames)

        def _run(cmd: list) -> bool:
            try:
                try:
                    if out_path.is_file():
                        out_path.unlink()
                except OSError:
                    pass
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=180,
                    check=False,
                )
                return (
                    r.returncode == 0
                    and out_path.is_file()
                    and out_path.stat().st_size > 0
                )
            except Exception:
                return False

        # 1) Retime video to wall-clock + full audio
        if _run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-filter_complex",
                f"[0:v]setpts=PTS*{pts_scale:.6f},fps={true_fps:.4f}[v]",
                "-map",
                "[v]",
                "-map",
                "1:a:0",
                "-c:v",
                "mjpeg",
                "-q:v",
                "5",
                "-c:a",
                "pcm_s16le",
                str(out_path),
            ]
        ):
            return True

        # 2) Fallback copy (may desync)
        if _run(
            [
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
                str(out_path),
            ]
        ):
            return True
        return False

    def _audio_duration_s(self, audio_path: Path) -> float:
        try:
            with wave.open(str(audio_path), "rb") as wf:
                fr = int(wf.getframerate()) or AUDIO_SAMPLE_RATE
                return float(wf.getnframes()) / float(fr)
        except Exception:
            return 0.0

    def _finalize_mp4(
        self,
        video_path: Path,
        audio_path: Optional[Path],
        out_path: Path,
        *,
        wall_s: float = 0.0,
        n_frames: int = 0,
    ) -> tuple[bool, str]:
        """Transcode MJPG temp + WAV → H.264 MP4. Returns (ok, encoder_tag).

        Retimes video to wall-clock (field-lite 7.5 stamp vs slower real FPS).
        """
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            return False, "none"
        if self._h264_encoder is None:
            self._h264_encoder = probe_h264_encoder(
                prefer_hardware=self._prefer_hw_encode
            )
        enc = self._h264_encoder or "none"
        if enc == "none":
            return False, "none"

        has_audio = bool(
            audio_path is not None
            and audio_path.is_file()
            and audio_path.stat().st_size > 44
        )
        true_fps = self._wall_video_fps(wall_s, n_frames)
        pts_scale = self._pts_scale_for_wall(wall_s, n_frames)
        aac = _ffmpeg_has_encoder(ffmpeg, "aac")
        acodec = "aac" if aac else "pcm_s16le"
        vfilter_base = f"setpts=PTS*{pts_scale:.6f},fps={true_fps:.4f}"

        def _run(cmd: list) -> bool:
            try:
                try:
                    if out_path.is_file():
                        out_path.unlink()
                except OSError:
                    pass
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=300,
                    check=False,
                )
                return (
                    r.returncode == 0
                    and out_path.is_file()
                    and out_path.stat().st_size > 0
                )
            except Exception:
                return False

        if enc == "vaapi":
            order = ["vaapi", "libx264"]
        elif enc == "libx264":
            order = ["libx264"]
        else:
            return False, "none"

        for which in order:
            if which == "vaapi":
                dev = _vaapi_render_device()
                if not dev:
                    continue
                vf = f"{vfilter_base},format=nv12,hwupload"
                cmd: list = [
                    ffmpeg,
                    "-y",
                    "-vaapi_device",
                    dev,
                    "-i",
                    str(video_path),
                ]
                if has_audio:
                    assert audio_path is not None
                    cmd += ["-i", str(audio_path)]
                cmd += ["-vf", vf, "-c:v", "h264_vaapi", "-b:v", "2M"]
                if has_audio:
                    cmd += [
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-c:a",
                        acodec,
                    ]
                    if aac:
                        cmd += ["-b:a", "128k"]
                cmd += ["-movflags", "+faststart", str(out_path)]
                if _run(cmd):
                    self._h264_encoder = "vaapi"
                    return True, "vaapi"
                continue

            if which == "libx264":
                cmd = [ffmpeg, "-y", "-i", str(video_path)]
                if has_audio:
                    assert audio_path is not None
                    cmd += ["-i", str(audio_path)]
                cmd += ["-vf", vfilter_base]
                cmd += [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "28",
                    "-pix_fmt",
                    "yuv420p",
                ]
                if has_audio:
                    cmd += [
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-c:a",
                        acodec,
                    ]
                    if aac:
                        cmd += ["-b:a", "128k"]
                cmd += ["-movflags", "+faststart", str(out_path)]
                if _run(cmd):
                    self._h264_encoder = "libx264"
                    return True, "libx264"
        return False, enc

    def start_record(
        self,
        bgr: np.ndarray,
        fps: float = 15.0,
        spectrum: Optional["SpectrumAnalyzer"] = None,
        *,
        record_format: str = "avi",
        hardware_encode: bool = False,
        h264_encoder: Optional[str] = None,
    ) -> Optional[Path]:
        if self._recording:
            return self._path
        if bgr is None or bgr.size == 0:
            self._set_flash("record failed: no frame")
            return None
        self.ensure_dir()
        h, w = bgr.shape[:2]
        ts = self._ts()
        fmt = "mp4" if (record_format or "avi").strip().lower() == "mp4" else "avi"
        self._record_format = fmt
        self._prefer_hw_encode = bool(hardware_encode) or fmt == "mp4"
        # Startup probe result (main.py); only re-probe if missing
        if h264_encoder:
            self._h264_encoder = str(h264_encoder)
        elif self._h264_encoder is None:
            self._h264_encoder = probe_h264_encoder(
                prefer_hardware=self._prefer_hw_encode
            )
        # Capture always MJPG temp AVI (reliable); finalize to AVI or MP4 on stop
        video_tmp = self.captures_dir / f"sls_{ts}_video.avi"
        audio_tmp = self.captures_dir / f"sls_{ts}_audio.wav"
        final = self.captures_dir / (
            f"sls_{ts}.mp4" if fmt == "mp4" else f"sls_{ts}.avi"
        )

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
            self._frame_count = 0
            self._record_started = time.time()
            self._record_gen = int(self._record_gen) + 1
            self._tts_clips = []

        enc_note = ""
        if fmt == "mp4":
            enc_note = f" →{self._h264_encoder or 'none'}"
        if audio_ok:
            self._set_flash(f"recording {final.name} +audio{enc_note}")
        else:
            self._set_flash(f"recording {video_tmp.name} (video only){enc_note}")
        self._log_event(
            "record_start",
            {
                "file": final.name,
                "format": fmt,
                "encoder": self._h264_encoder if fmt == "mp4" else "mjpg",
                "nominal_fps": float(fps),
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
            with self._lock:
                self._frame_count = int(self._frame_count) + 1
        except Exception:
            pass

    def stop_record(self) -> Optional[Path]:
        path = self._path
        video_tmp = self._video_tmp
        audio_tmp = self._audio_tmp
        elapsed = self.recording_elapsed_str() if self._recording else "0:00"
        # Snapshot capture stats before stop clears streams / spectrum sink
        with self._lock:
            n_chunks = len(self._audio_chunks)
            n_pcm = int(getattr(self, "_pcm_samples", 0) or 0)
            n_tts = len(self._tts_clips)
            n_frames = int(self._frame_count)
            had_tts = n_tts > 0
            had_audio = bool(self._has_audio) or n_pcm > 0 or n_chunks > 0 or had_tts
            via_spectrum = bool(self._via_spectrum)
            if self._writer is not None:
                try:
                    self._writer.release()
                except Exception:
                    pass
            self._writer = None
            self._recording = False
            # keep _record_started until mix so elapsed length works
            rec_started = self._record_started

        self._stop_audio_capture()

        wall_s = 0.0
        if rec_started > 0:
            wall_s = max(0.0, time.time() - float(rec_started))
        true_fps = self._wall_video_fps(wall_s, n_frames)

        final_path = path
        audio_saved = False
        muxed = False
        encoder_used = "mjpg"
        want_mp4 = (self._record_format or "avi").lower() == "mp4"
        if (had_audio or had_tts) and audio_tmp is not None:
            # restore start for mix length if needed
            if self._record_started <= 0 and rec_started > 0:
                self._record_started = rec_started
            audio_saved = self._write_wav(audio_tmp)
            self._record_started = 0.0
        else:
            self._record_started = 0.0

        def _cleanup_temps() -> None:
            for tmp in (video_tmp, audio_tmp):
                if tmp is None:
                    continue
                try:
                    tmp.unlink(missing_ok=True)
                except TypeError:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass

        if video_tmp is not None and video_tmp.is_file() and path is not None:
            if want_mp4:
                # Prefer MP4 H.264; on failure fall back to AVI mux (#20)
                mp4_ok, enc_tag = self._finalize_mp4(
                    video_tmp,
                    audio_tmp if audio_saved else None,
                    path,
                    wall_s=wall_s,
                    n_frames=n_frames,
                )
                if mp4_ok:
                    muxed = True
                    encoder_used = enc_tag
                    final_path = path
                    self._path = final_path
                    _cleanup_temps()
                    self._set_flash(
                        f"saved {final_path.name} +audio ({elapsed}) [{enc_tag}]"
                    )
                else:
                    # Fallback AVI (same take stem)
                    avi_path = path.with_suffix(".avi")
                    if audio_saved and audio_tmp is not None:
                        muxed = self._mux_av(
                            video_tmp,
                            audio_tmp,
                            avi_path,
                            wall_s=wall_s,
                            n_frames=n_frames,
                        )
                    if muxed:
                        _cleanup_temps()
                        final_path = avi_path
                        self._path = final_path
                        self._set_flash(
                            f"mp4 unavailable — saved {final_path.name} +audio "
                            f"({elapsed})"
                        )
                    elif audio_saved and audio_tmp is not None:
                        final_path = video_tmp
                        self._path = video_tmp
                        self._set_flash(
                            f"saved {video_tmp.name} + {audio_tmp.name} ({elapsed})"
                            " — install ffmpeg for mux/mp4"
                        )
                    else:
                        try:
                            video_tmp.rename(avi_path)
                            final_path = avi_path
                        except OSError:
                            final_path = video_tmp
                        self._path = final_path
                        self._set_flash(
                            f"mp4 unavailable — saved {final_path.name} ({elapsed})"
                        )
            elif audio_saved and audio_tmp is not None:
                muxed = self._mux_av(
                    video_tmp,
                    audio_tmp,
                    path,
                    wall_s=wall_s,
                    n_frames=n_frames,
                )
                if muxed:
                    _cleanup_temps()
                    final_path = path
                    self._path = final_path
                    self._set_flash(f"saved {final_path.name} +audio ({elapsed})")
                else:
                    final_path = video_tmp
                    self._path = video_tmp
                    self._set_flash(
                        f"saved {video_tmp.name} + {audio_tmp.name} ({elapsed})"
                        " — install ffmpeg or imageio-ffmpeg to mux"
                    )
            else:
                # Video-only: rename temp to final container name
                try:
                    if path.suffix.lower() == ".mp4":
                        # video-only mp4 without encode path — keep avi temp name
                        avi_path = path.with_suffix(".avi")
                        video_tmp.rename(avi_path)
                        final_path = avi_path
                    else:
                        video_tmp.rename(path)
                        final_path = path
                except OSError:
                    final_path = video_tmp
                self._path = final_path
                if had_tts and not audio_saved:
                    self._set_flash(
                        f"saved {final_path.name} ({elapsed}) — TTS not in file"
                    )
                else:
                    self._set_flash(f"saved {final_path.name} ({elapsed})")
        else:
            self._set_flash("record stop: no file")

        self._log_event(
            "record_stop",
            {
                "file": final_path.name if final_path else None,
                "elapsed": elapsed,
                "muxed": muxed,
                "format": self._record_format,
                "encoder": encoder_used,
                "audio": audio_saved,
                "had_tts": had_tts,
                "pcm_samples": n_pcm,
                "pcm_chunks": n_chunks,
                "tts_clips": n_tts,
                "via_spectrum": via_spectrum,
                "video_frames": n_frames,
                "wall_s": round(wall_s, 3),
                "nominal_fps": float(self._fps or 0),
                "true_fps": round(true_fps, 3),
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

    def note_drakevox(self, word: str) -> None:
        self._log_event("drakevox", {"word": word})
        self._set_flash(f"DRAKEVOX: {word}", seconds=4.0)

    def note_detection(
        self,
        detected: int,
        auto_snap: bool = False,
        bgr: Optional[np.ndarray] = None,
    ) -> Optional[str]:
        """Track pose appear/disappear. Returns 'appear' | 'disappear' | None.

        Auto-snap is handled by the UI so DrakeVox can be composited into the JPEG.
        ``auto_snap`` / ``bgr`` kept for call-site compatibility (unused for save).
        """
        prev = self._last_detected
        cur = int(detected)
        event: Optional[str] = None
        if cur > 0 and prev == 0:
            self._log_event("detect_appear", {"detected": cur})
            event = "appear"
        elif cur == 0 and prev > 0:
            self._log_event("detect_disappear", {"detected": 0})
            event = "disappear"
        self._last_detected = cur
        return event
