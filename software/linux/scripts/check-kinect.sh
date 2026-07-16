#!/usr/bin/env bash
# Smoke-check Xbox 360 Kinect presence and Linux driver state.
set -euo pipefail

echo "=== SLS / Kinect check ==="
echo "Host: $(hostname)  Date: $(date -Iseconds)"
echo

echo "--- USB (Microsoft 045e / NUI) ---"
if command -v lsusb >/dev/null 2>&1; then
  lsusb | grep -E '045e|Kinect|NUI|Xbox' || echo "(no matching USB devices)"
else
  echo "lsusb not installed"
fi
echo

echo "--- Expected Kinect 360 IDs ---"
echo "  045e:02b0 motor | 045e:02ad audio | 045e:02ae camera"
echo

echo "--- Kernel modules ---"
lsmod | grep -E 'gspca|kinect|videodev' || echo "(none of gspca/kinect/videodev loaded)"
echo

echo "--- V4L devices ---"
if ls /dev/video* >/dev/null 2>&1; then
  ls -la /dev/video*
else
  echo "(no /dev/video* — normal if only freenect is used and gspca is blacklisted)"
fi
echo

if command -v v4l2-ctl >/dev/null 2>&1; then
  echo "--- v4l2-ctl --list-devices ---"
  v4l2-ctl --list-devices 2>/dev/null || true
  echo
fi

echo "--- freenect tools ---"
if command -v freenect-glview >/dev/null 2>&1; then
  echo "freenect-glview: $(command -v freenect-glview)"
  dpkg -l 'libfreenect*' 'freenect' 2>/dev/null | grep -E '^ii' || true
else
  echo "freenect-glview not found — install: sudo apt install freenect libfreenect-bin"
fi
echo

echo "--- Groups (need video/plugdev for device access) ---"
id
echo

echo "--- Blacklist file ---"
if [[ -f /etc/modprobe.d/blacklist-gspca-kinect.conf ]]; then
  cat /etc/modprobe.d/blacklist-gspca-kinect.conf
else
  echo "(no /etc/modprobe.d/blacklist-gspca-kinect.conf)"
fi
echo

echo "=== Done ==="
echo "Depth test when ready: freenect-glview"
echo "Setup docs: software/linux/docs/UBUNTU-SETUP.md"
