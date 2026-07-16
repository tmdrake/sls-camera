# Bring-up log: freenect depth video (M0)

**Status:** **Working** — live Kinect video via `freenect-glview` on the OptiPlex host.  
**Date:** 2026-07-16  
**Host:** `tmdrake-optiplex7050` (Ubuntu 26.04 LTS)  
**Sensor:** Xbox 360 Kinect (NUI Motor / Audio / Camera)

## Goal (M0)

Prove the Linux path can open the Kinect and show a live freenect view (depth/RGB style demo), not just the kernel RGB webcam (`gspca_kinect`).

**Result:** Achieved. Operator confirmed video from freenect.

## Hardware that worked

| Item | Detail |
|------|--------|
| Kinect model | Xbox 360 / original NUI |
| USB IDs | `045e:02b0` motor, `045e:02ad` audio, `045e:02ae` camera |
| Power | External Kinect power brick (required) |
| Host | Dell OptiPlex 7050 class PC, Ubuntu 26.04 |

## Software that worked

| Package | Version (Ubuntu) |
|---------|------------------|
| `freenect` (metapackage) | `1:0.5.3-3.3` |
| `libfreenect-bin` | `1:0.5.3-3.3` (provides `freenect-glview`) |
| `libfreenect0.5t64` | `1:0.5.3-3.3` |
| Udev rules | `/lib/udev/rules.d/60-libfreenect0.5t64.rules` |

Primary test command:

```bash
freenect-glview
```

Smoke check:

```bash
./software/linux/scripts/check-kinect.sh
```

## Procedure that got us there

1. **Install freenect stack**  
   `sudo apt install freenect libfreenect-bin libfreenect-dev v4l-utils`  
   (also covered by `software/linux/scripts/install-freenect.sh`)

2. **Blacklist kernel webcam driver** so freenect can claim the camera  
   ```bash
   echo 'blacklist gspca_kinect' | sudo tee /etc/modprobe.d/blacklist-gspca-kinect.conf
   sudo modprobe -r gspca_kinect
   ```
   Important: the blacklist only prevents *future* loads. If `gspca_kinect` is already in RAM, unload it explicitly.

3. **Groups**  
   User in `plugdev` (required by freenect udev rules) and preferably `video`.  
   Log out/in or open a new session after `usermod -aG`.

4. **Apply freenect udev permissions**  
   After package install, re-trigger USB or unplug/replug Kinect USB:  
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=045e
   ```  
   Working node shape observed:  
   `crw-rw-rw- 1 root plugdev ...` on motor/audio/camera under `/dev/bus/usb/...`

5. **Run viewer**  
   `freenect-glview` with a normal desktop display (`DISPLAY=:0`).

Helper script for the access failures: `software/linux/scripts/fix-kinect-access.sh`.

## Failure we hit (and fix)

### Symptom

```text
Number of devices found: 1
Could not open camera: -3
Failed to open camera subdevice or it is not disabled.
Failed to open motor subdevice or it is not disabled.
Failed to open audio subdevice or it is not disabled.
Could not open device
```

### Root causes (both present)

| Cause | Evidence | Fix |
|-------|----------|-----|
| Kernel driver still bound | `lsmod` showed `gspca_kinect` after blacklist file existed | `sudo modprobe -r gspca_kinect` (and keep blacklist) |
| USB not writable by user | nodes were `root:root` `rw-rw-r--` (no write for user) → libusb **-3** `LIBUSB_ERROR_ACCESS` | reload/trigger udev freenect rules (`MODE="0666"`, `GROUP="plugdev"`) or unplug/replug |

Error **-3** = access denied on USB.  
“**subdevice … not disabled**” = kernel interface still claimed (typically `gspca_kinect`).

## Working-state checklist (recreate on a new machine)

- [ ] `lsusb` shows `02b0` / `02ad` / `02ae`
- [ ] Packages: `freenect`, `libfreenect-bin` installed
- [ ] `/etc/modprobe.d/blacklist-gspca-kinect.conf` present
- [ ] `lsmod \| grep gspca` empty **or** freenect still opens after unload (prefer empty)
- [ ] Kinect USB nodes group `plugdev` and mode allows write (`0666` as shipped by package rules)
- [ ] User session includes `plugdev`
- [ ] `freenect-glview` shows live video

## What M0 is *not*

- Not the full Ghost Hunters SLS stick-figure UI yet  
- Not skeleton tracking on Linux yet  
- Not the Windows WPF SLS Explorer (`software/source/`)  

Next milestone: `software/linux/viewer/` custom depth-first + stick-figure UI (see `docs/ARCHITECTURE.md`).

## Related docs

- [UBUNTU-SETUP.md](../docs/UBUNTU-SETUP.md) — install and troubleshooting  
- [MACHINE-STATUS.md](MACHINE-STATUS.md) — host snapshot  
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) — stack and milestones  
