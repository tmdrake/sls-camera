#!/usr/bin/env bash
# Start SLS viewer — Qt fullscreen always-on-top by default.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PATH="${HOME}/.local/bin:${PATH}"

# True if any arg is -h / --help (skip noisy preflight for help only)
_want_help=0
for _a in "$@"; do
  case "$_a" in
    -h|--help) _want_help=1; break ;;
  esac
done

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating venv with uv..."
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  uv venv .venv --python python3
  uv pip install --python .venv/bin/python -r requirements.txt
fi

# Ensure Qt is present (added after first web-only install)
if ! .venv/bin/python -c "import PySide6" 2>/dev/null; then
  echo "Installing PySide6..."
  uv pip install --python .venv/bin/python 'PySide6>=6.6'
fi

MODEL="models/pose_landmarker_lite.task"
if [[ ! -f "$MODEL" ]]; then
  echo "Downloading MediaPipe pose model..."
  mkdir -p models
  curl -L --fail -o "$MODEL" \
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
fi

if [[ "$_want_help" -eq 0 ]]; then
  if lsmod 2>/dev/null | grep -q '^gspca_kinect'; then
    echo "WARNING: gspca_kinect is loaded — freenect usually cannot open the Kinect."
    echo "  Fix:  sudo modprobe -r gspca_kinect"
    echo "  Or:   ../scripts/fix-kinect-access.sh"
  fi

  # Spectrum / sounddevice needs PortAudio. Prefer loading the .so (works even if
  # ldconfig cache is incomplete); also check common multiarch paths.
  _portaudio_ok=0
  if .venv/bin/python -c "import ctypes; ctypes.CDLL('libportaudio.so.2')" 2>/dev/null; then
    _portaudio_ok=1
  elif ldconfig -p 2>/dev/null | grep -qi 'libportaudio\.so'; then
    _portaudio_ok=1
  elif compgen -G '/usr/lib/*/libportaudio.so*' >/dev/null 2>&1; then
    _portaudio_ok=1
  fi
  if [[ "$_portaudio_ok" -eq 0 ]]; then
    echo "NOTE: libportaudio not found — spectrum may stay off until:"
    echo "  sudo apt install libportaudio2"
  fi

  echo "Starting SLS viewer (Qt fullscreen always-on-top)..."
fi

# Pass-through args, e.g.:
#   ./run.sh --help
#   ./run.sh --demo          # fallback synthetic frames only if Kinect will not open
#   ./run.sh --mirror --led-off
exec .venv/bin/python -m sls_viewer "$@"
