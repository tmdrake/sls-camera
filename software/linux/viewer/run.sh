#!/usr/bin/env bash
# Start SLS viewer — Qt fullscreen always-on-top by default.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PATH="${HOME}/.local/bin:${PATH}"

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

if lsmod 2>/dev/null | grep -q '^gspca_kinect'; then
  echo "WARNING: gspca_kinect is loaded — freenect usually cannot open the Kinect."
  echo "  Fix:  sudo modprobe -r gspca_kinect"
  echo "  Or:   ../scripts/fix-kinect-access.sh"
fi

echo "Starting SLS viewer (Qt fullscreen always-on-top)..."
# Default UI is qt; pass --ui web for browser, --demo for synthetic frames
exec .venv/bin/python -m sls_viewer "$@"
