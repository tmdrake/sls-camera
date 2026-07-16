#!/usr/bin/env bash
# Install libfreenect and prepare this machine for Kinect depth (SLS M0).
# Run in a normal terminal so sudo can prompt for your password:
#   ./software/linux/scripts/install-freenect.sh
set -euo pipefail

echo "=== Install freenect + prep Kinect depth ==="

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Do not run as root; run as your user so groups apply correctly."
  exit 1
fi

sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
  freenect libfreenect-bin libfreenect-dev v4l-utils

echo "Adding $USER to video group (log out/in after this script)..."
sudo usermod -aG video "$USER"

echo "Blacklisting gspca_kinect so freenect can own the device..."
echo 'blacklist gspca_kinect' | sudo tee /etc/modprobe.d/blacklist-gspca-kinect.conf

if lsmod | grep -q '^gspca_kinect'; then
  echo "Unloading gspca_kinect..."
  if fuser /dev/video0 >/dev/null 2>&1; then
    echo "WARNING: something is using /dev/video0:"
    fuser -v /dev/video0 2>&1 || true
    echo "Close Cheese/browser/OBS camera, then re-run:"
    echo "  sudo modprobe -r gspca_kinect"
  else
    sudo modprobe -r gspca_kinect || {
      echo "Could not unload gspca_kinect; try after closing camera apps:"
      echo "  sudo modprobe -r gspca_kinect"
    }
  fi
fi

echo
echo "=== freenect tools ==="
command -v freenect-glview
dpkg -l freenect libfreenect-bin 2>/dev/null | grep '^ii' || true

echo
echo "=== module state ==="
lsmod | grep gspca || echo "gspca not loaded (good for freenect)"

echo
echo "=== USB Kinect ==="
lsusb | grep -E '045e:02(b0|ad|ae)' || lsusb | grep 045e || echo "Kinect not seen on USB"

echo
echo "=== Next ==="
echo "1. If this is the first time adding the video group: log out and back in."
echo "2. With Kinect powered and plugged in, run:"
echo "     freenect-glview"
echo "3. Or smoke check:"
echo "     $(cd "$(dirname "$0")/../../.." && pwd)/software/linux/scripts/check-kinect.sh"
echo
echo "Done."
