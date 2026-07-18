# Ubuntu setup — Xbox 360 Kinect for SLS work

**Verified working (M0):** 2026-07-16 on `tmdrake-optiplex7050`, Ubuntu 26.04, Kinect 360 — `freenect-glview` shows live video.

Full narrative of the first successful bring-up: [../notes/BRINGUP-FREENECT.md](../notes/BRINGUP-FREENECT.md).

## Hardware checklist

- [x] Kinect **external power supply** plugged in (required)
- [x] USB connected (prefer USB 2.0 or a solid powered hub if flaky)
- [x] Confirm devices appear:

```bash
lsusb | grep -i '045e'
```

Expected for original Xbox 360 Kinect:

| ID | Product |
|----|---------|
| `045e:02b0` | Xbox NUI Motor |
| `045e:02ad` | Xbox NUI Audio |
| `045e:02ae` | Xbox NUI Camera |

## Two drivers, one device

| Driver / stack | What you get | SLS useful? |
|----------------|--------------|-------------|
| Kernel `gspca_kinect` | RGB (and limited V4L) as `/dev/video0` | No — not full depth/skeleton |
| **libfreenect** (`freenect-glview`) | Depth + RGB + IR + motor/tilt | Yes — depth base for SLS UI |

**Rule:** when using freenect for depth, **blacklist** `gspca_kinect` so it does not own the camera.  
**Also unload it** if it is already loaded — blacklist alone does not kick an in-memory module.

## Install packages

```bash
sudo apt update
sudo apt install -y freenect libfreenect-bin libfreenect-dev \
  v4l-utils guvcview
```

Or from this repo (preferred for field app + offline cache):

```bash
# Full seed list (freenect, portaudio, espeak, python3-venv, ffmpeg, …)
./software/linux/scripts/install-apt-deps.sh
# or via installer:
./software/linux/scripts/install-field-app.sh --with-apt-deps

# Offline: use firmware recursive deb pack (never dpkg -i *.deb)
./software/linux/scripts/install-apt-deps.sh \
  --deb-cache ~/sls-camera-firmware/vendor/debs
```

See [FIELD-INSTALL.md](FIELD-INSTALL.md) and issues [#2](https://github.com/tmdrake/sls-camera/issues/2) / [#3](https://github.com/tmdrake/sls-camera/issues/3).

Legacy freenect-only helper:

```bash
./software/linux/scripts/install-freenect.sh
```

Verified package set on Ubuntu 26.04: `freenect` / `libfreenect-bin` **1:0.5.3-3.3**.

Optional later (skeleton / Python viewer):

```bash
sudo apt install -y python3-pip python3-venv python3-opencv
# freenect Python bindings vary by distro; may need source build
```

## Kinect microphone (spectrum strip)

The Xbox 360 Kinect has a **4-mic array** (USB **NUI Audio** `045e:02ad`). Out of the box it is **not** a normal ALSA sound card until **audio firmware** is loaded.

### One-time setup (recommended for field spectrum)

```bash
sudo apt install -y kinect-audio-setup alsa-utils libportaudio2
# Package downloads non-redistributable UAC firmware from Microsoft
# (debconf license prompts). See package description / MS Kinect SDK ToS.
```

Then **unplug and replug** the Kinect (or reboot) so udev can load firmware. Check:

```bash
arecord -l
# Expect a USB Audio capture device (name may include USB / Microsoft)
./software/linux/scripts/check-kinect.sh
```

After that, the SLS viewer **spectrum strip** and **Record audio** prefer a Kinect/USB capture device, else fall back to the system default mic. Recordings are muxed into an AVI with PCM audio (see `viewer/README.md`). The app does **not** change ALSA/Pulse capture gain — use system volume tools if levels are wrong.

### If install fails: `Invalid hash for file 'KinectSDK-…msi'`

Microsoft re-hosted the Beta 2 MSI; its **MD5 no longer matches** the hard-coded checksum in `/usr/sbin/kinect_fetch_fw`. The download can succeed and still fail configure.

**Manual recovery (accept MS SDK license yourself):**

```bash
# 1) Finish/clear the broken package state after firmware is in place (see below)
# 2) Fetch MSI and extract UAC firmware yourself
TMP=$(mktemp -d) && cd "$TMP"
URL="http://download.microsoft.com/download/F/9/9/F99791F2-D5BE-478A-B77A-830AD14950C3/KinectSDK-v1.0-beta2-x86.msi"
wget -O KinectSDK-v1.0-beta2-x86.msi "$URL"
md5sum KinectSDK-v1.0-beta2-x86.msi   # note actual hash
sudo apt install -y 7zip wget   # provides 7z
7z e -y -r KinectSDK-v1.0-beta2-x86.msi "UACFirmware.*"

# 3) Install firmware where udev expects it
sudo mkdir -p /lib/firmware/kinect
# file name is often like UACFirmware.01 or similar — pick the extracted blob:
sudo install -m 644 UACFirmware.* /lib/firmware/kinect/UACFirmware

# 4) Patch the fetch script hash to the actual MD5 so dpkg can finish
ACTUAL=$(md5sum KinectSDK-v1.0-beta2-x86.msi | awk '{print $1}')
sudo sed -i "s/^SDK_MD5=.*/SDK_MD5=\"$ACTUAL\"/" /usr/sbin/kinect_fetch_fw
sudo kinect_fetch_fw /lib/firmware/kinect
sudo dpkg --configure -a

# 5) Reload rules and replug Kinect
sudo udevadm control --reload-rules
# unplug / replug Kinect USB (power can stay on)
arecord -l
```

If `7z e` finds no `UACFirmware.*`, list archive contents: `7z l KinectSDK-v1.0-beta2-x86.msi | grep -i UAC`.

**Workaround without Kinect mic:** spectrum still uses the **system default mic** when PortAudio works (`libportaudio2`). Depth/SLS does not need audio firmware.

**Notes**

- Firmware is **not** redistributed in this git repo.  
- This is independent of freenect depth/IR (depth uses the camera USB interface).  
- freenect’s raw 4-mic API is **not** used by the current viewer (ALSA UAC path only).

## User groups

```bash
sudo usermod -aG video,plugdev "$USER"
# log out and back in (or new login session) so groups apply
```

Freenect’s udev rules use **`GROUP="plugdev"`** and **`MODE="0666"`** for the three Kinect USB IDs. Session must include `plugdev` for reliable access (mode 0666 also allows any user once rules applied).

## Blacklist gspca (for freenect depth)

```bash
echo 'blacklist gspca_kinect' | sudo tee /etc/modprobe.d/blacklist-gspca-kinect.conf
sudo modprobe -r gspca_kinect   # required if already loaded
```

Unload any app using `/dev/video0` first (Cheese, browser, OBS, etc.) if unload fails.

To reverse (RGB webcam only again):

```bash
sudo rm /etc/modprobe.d/blacklist-gspca-kinect.conf
sudo modprobe gspca_kinect
```

## Udev permissions (after first install)

Package rules: `/lib/udev/rules.d/60-libfreenect0.5t64.rules`.

If the Kinect was already plugged in when freenect was installed, re-apply rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=045e
# or unplug Kinect USB (power brick can stay on), wait, replug
```

Working permission shape:

```text
crw-rw-rw- 1 root plugdev ... /dev/bus/usb/...  (motor, audio, camera)
```

## First tests

```bash
# from repo root
./software/linux/scripts/check-kinect.sh

# depth / RGB OpenGL demo (M0 success criteria)
freenect-glview
```

### M0 success criteria (met on this host)

- Kinect listed by freenect (`Number of devices found: 1` is normal)
- Window opens with **live video** (depth/color freenect view)
- No `Could not open camera: -3` / subdevice failures

## Troubleshooting: could not open camera

Common error (seen during first bring-up, then fixed):

```text
Number of devices found: 1
Could not open camera: -3
Failed to open camera subdevice or it is not disabled.
Failed to open motor subdevice or it is not disabled.
...
```

That almost always means **both** of:

1. **`gspca_kinect` still loaded** (blacklist file does not unload a module already in RAM)
2. **USB nodes still without write access** (udev rules apply only after reload + re-trigger or unplug/replug)

| Code / message | Meaning |
|----------------|---------|
| `-3` | libusb access denied (permissions) |
| subdevice not disabled | kernel driver still bound to interface |

Fix (needs sudo in a real terminal):

```bash
./software/linux/scripts/fix-kinect-access.sh
# open a NEW terminal so video/plugdev groups apply
freenect-glview
```

Manual equivalent:

```bash
sudo modprobe -r gspca_kinect
lsmod | grep gspca || echo "gspca clear"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=045e
# or unplug/replug Kinect USB cable
# log out/in if `groups` does not list plugdev and video
```

Still stuck:

1. Confirm power brick is on  
2. Confirm `gspca_kinect` is not loaded: `lsmod | grep gspca`  
3. Check USB is writable: Kinect nodes under `/dev/bus/usb/` should be `0666` or group `plugdev` with write  
4. Try another USB port  
5. Re-run `check-kinect.sh`  
6. See [BRINGUP-FREENECT.md](../notes/BRINGUP-FREENECT.md)

## RGB-only path (no freenect)

If you only need a normal camera picture:

1. Do **not** blacklist `gspca_kinect` (or load it again)
2. Open `guvcview` or similar on `/dev/video0`

This is **not** the SLS look.

## Next after freenect works (M0 done)

1. Capture depth frames in a small Python viewer (`viewer/`)
2. Add skeleton / body stick figures (MediaPipe or OpenNI/NiTE if revived)
3. Dark UI + depth-first layout matching Windows SLS Explorer notes
