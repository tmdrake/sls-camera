#!/usr/bin/env bash
# Fix freenect "Could not open camera: -3" / subdevice failures on Ubuntu.
# Causes this script addresses:
#   1) gspca_kinect still bound to the camera
#   2) USB device nodes not reloaded with freenect udev rules (0666 + plugdev)
#
# Run in a real terminal (needs sudo password):
#   ./software/linux/scripts/fix-kinect-access.sh
set -euo pipefail

echo "=== Fix Kinect access for freenect ==="

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as your normal user (script will sudo)."
  exit 1
fi

# Ensure blacklist exists
if [[ ! -f /etc/modprobe.d/blacklist-gspca-kinect.conf ]]; then
  echo 'blacklist gspca_kinect' | sudo tee /etc/modprobe.d/blacklist-gspca-kinect.conf
fi

# Ensure user is in groups freenect/udev expect
sudo usermod -aG video,plugdev "$USER"

# Close nothing automatically; just report holders of /dev/video0
if [[ -e /dev/video0 ]] && fuser /dev/video0 >/dev/null 2>&1; then
  echo "WARNING: /dev/video0 is in use — close these apps then re-run if unload fails:"
  fuser -v /dev/video0 2>&1 || true
fi

echo "Unloading gspca_kinect (required so freenect can open camera)..."
if lsmod | grep -q '^gspca_kinect'; then
  sudo modprobe -r gspca_kinect || {
    echo "FAILED to unload gspca_kinect."
    echo "Close any camera app, then: sudo modprobe -r gspca_kinect"
    exit 1
  }
fi
lsmod | grep gspca && echo "WARN: gspca still present" || echo "gspca unloaded OK"

echo "Reloading udev rules for freenect (MODE 0666, GROUP plugdev)..."
sudo udevadm control --reload-rules
# Re-apply rules to Microsoft Kinect USB devices
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=045e
sleep 1

echo
echo "=== USB device permissions (want root:plugdev or mode rw for all) ==="
for id in 02b0 02ad 02ae; do
  for dev in /dev/bus/usb/*/*; do
    if udevadm info -q property -n "$dev" 2>/dev/null | grep -q "ID_MODEL_ID=$id"; then
      ls -la "$dev"
    fi
  done
done

echo
echo "=== Quick permission test (need write on USB nodes) ==="
python3 - <<'PY'
import os
ok = True
for path in sorted(__import__("glob").glob("/dev/bus/usb/*/*")):
    try:
        import subprocess
        out = subprocess.check_output(["udevadm", "info", "-q", "property", "-n", path], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        continue
    if "ID_VENDOR_ID=045e" not in out:
        continue
    if "ID_MODEL_ID=02b0" in out or "ID_MODEL_ID=02ad" in out or "ID_MODEL_ID=02ae" in out:
        w = os.access(path, os.W_OK)
        print(path, "writable=" + str(w))
        ok = ok and w
print("PASS" if ok else "FAIL — if not writable, unplug/replug Kinect USB or reboot")
PY

echo
echo "=== Groups in THIS shell ==="
id
if ! id -nG | tr ' ' '\n' | grep -qx plugdev; then
  echo "NOTE: plugdev not in this shell yet — open a NEW terminal or log out/in."
fi
if ! id -nG | tr ' ' '\n' | grep -qx video; then
  echo "NOTE: video not in this shell yet — open a NEW terminal or log out/in."
fi

echo
echo "=== Test ==="
echo "In a NEW terminal (so groups apply), with DISPLAY set:"
echo "  freenect-glview"
echo
echo "If still failing, hard reset the USB device:"
echo "  unplug Kinect USB (leave power brick on), wait 3s, plug back in"
echo "  then: freenect-glview"
echo
echo "Done."
