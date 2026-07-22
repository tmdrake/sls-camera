"""TTS × recording: inject must not break or pollute AVI mixes."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from sls_viewer.session_io import AUDIO_SAMPLE_RATE, SessionRecorder


def _tone(n: int, amp: float = 0.5) -> np.ndarray:
    t = np.linspace(0, 1, n, endpoint=False, dtype=np.float32)
    return (amp * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)


def test_inject_mixes_with_mic_chunks(tmp_path: Path) -> None:
    rec = SessionRecorder(captures_dir=tmp_path)
    # Simulate start without opening real video/mic
    with rec._lock:
        rec._recording = True
        rec._record_started = time.time() - 1.0
        rec._record_gen = 1
        rec._tts_clips = []
        rec._audio_chunks = []

    # 0.5s of silence "mic"
    mic = np.zeros(AUDIO_SAMPLE_RATE // 2, dtype=np.float32)
    rec._on_pcm(mic)

    # TTS at +0.1s into the take
    when = rec._record_started + 0.1
    tone = _tone(AUDIO_SAMPLE_RATE // 10)  # 0.1s
    rec.inject_tts(tone, when, record_gen=1)

    mixed = rec._mix_audio()
    assert mixed is not None
    assert mixed.size >= AUDIO_SAMPLE_RATE // 2
    # Peak in TTS region should be non-zero
    start = int(0.1 * AUDIO_SAMPLE_RATE)
    region = mixed[start : start + tone.size]
    assert float(np.max(np.abs(region))) > 0.1


def test_stale_gen_dropped(tmp_path: Path) -> None:
    rec = SessionRecorder(captures_dir=tmp_path)
    with rec._lock:
        rec._recording = True
        rec._record_started = time.time()
        rec._record_gen = 2
        rec._tts_clips = []

    tone = _tone(800)
    # Wrong generation (previous take)
    rec.inject_tts(tone, time.time(), record_gen=1)
    assert rec._tts_clips == []

    # Matching generation accepted
    rec.inject_tts(tone, time.time(), record_gen=2)
    assert len(rec._tts_clips) == 1


def test_negative_offset_not_clamped_to_zero(tmp_path: Path) -> None:
    """Late worker from prior take must not land at t=0 of the new REC."""
    rec = SessionRecorder(captures_dir=tmp_path)
    t_start = time.time()
    with rec._lock:
        rec._recording = True
        rec._record_started = t_start
        rec._record_gen = 3
        rec._tts_clips = []

    tone = _tone(500)
    # Speak was queued 2s before this recording started
    rec.inject_tts(tone, t_start - 2.0, record_gen=3)
    assert rec._tts_clips == [], "stale pre-REC TTS must be dropped, not pasted at 0"


def test_inject_ignored_when_not_recording(tmp_path: Path) -> None:
    rec = SessionRecorder(captures_dir=tmp_path)
    rec.inject_tts(_tone(100), time.time(), record_gen=1)
    assert rec._tts_clips == []


def test_tts_only_timeline(tmp_path: Path) -> None:
    """No mic chunks still produces audio from TTS alone."""
    rec = SessionRecorder(captures_dir=tmp_path)
    t0 = time.time()
    with rec._lock:
        rec._recording = True
        rec._record_started = t0
        rec._record_gen = 1
        rec._tts_clips = []
        rec._audio_chunks = []

    rec.inject_tts(_tone(AUDIO_SAMPLE_RATE // 5), t0 + 0.05, record_gen=1)
    mixed = rec._mix_audio()
    assert mixed is not None and mixed.size > 100
    assert float(np.max(np.abs(mixed))) > 0.05
