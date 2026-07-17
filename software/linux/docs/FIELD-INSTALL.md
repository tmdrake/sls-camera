# Field app install (dev packaging)

**Stay in dev:** this documents how to wire a **git checkout** of the SLS Qt app on a Linux host (OptiPlex, tablet prototype, etc.). It is **not** a flashable tablet firmware image.

Target product path (later): **tablets** with Kinect, then sensor inputs and **stable external power** so SLS runs as a field appliance. Those steps are backlog — see below and [docs/TODO.md](../../../docs/TODO.md).

## Scripts

| Script | Role |
|--------|------|
| [`../scripts/install-field-app.sh`](../scripts/install-field-app.sh) | Install user launcher + optional login autostart |
| [`../scripts/uninstall-field-app.sh`](../scripts/uninstall-field-app.sh) | Remove what install added |
| [`../scripts/fix-kinect-access.sh`](../scripts/fix-kinect-access.sh) | gspca unload + freenect udev (sudo) |
| [`../scripts/install-freenect.sh`](../scripts/install-freenect.sh) | Host freenect packages |
| [`../scripts/check-kinect.sh`](../scripts/check-kinect.sh) | Quick USB / freenect health |

### Install (typical dev machine)

```bash
# from repo root
./software/linux/scripts/install-field-app.sh

# launcher only (no login autostart) — good for daily dev
./software/linux/scripts/install-field-app.sh --no-autostart

# fuller host prep (sudo)
./software/linux/scripts/install-field-app.sh \
  --with-apt-deps \
  --with-kinect-access
```

### What install places on disk

| Path | Purpose |
|------|---------|
| `~/.local/bin/sls-camera` | Wrapper → `software/linux/viewer/run.sh` in **this** clone |
| `~/.local/share/applications/sls-camera.desktop` | App menu entry |
| `~/.config/autostart/sls-camera.desktop` | Autostart after graphical login (optional) |
| `~/.local/share/sls-camera/install-manifest.txt` | Paths for uninstall |

Does **not** copy the tree system-wide. Moving/renaming the repo breaks the wrapper until you re-run install.

### Uninstall

```bash
./software/linux/scripts/uninstall-field-app.sh
# stop autostart only, keep menu launcher:
./software/linux/scripts/uninstall-field-app.sh --keep-launcher
```

Leaves: git repo, `viewer/.venv`, captures, apt packages, gspca blacklist (if you used `--with-kinect-access`).

## Still manual / separate

| Item | Notes |
|------|--------|
| **Kinect USB Audio** | `sudo apt install kinect-audio-setup` (+ MSI hash recovery in [UBUNTU-SETUP.md](UBUNTU-SETUP.md)) |
| **First run** | `run.sh` builds venv, downloads MediaPipe model (network once) |
| **DISPLAY** | Needs a logged-in desktop session for Qt |

## Dev vs tablet firmware (roadmap)

```text
Now (dev)
  git clone → install-field-app.sh → sls-camera / optional autostart
       │
Later (tablet appliance)
  clean desktop chrome (no stock Lubuntu clutter)
  firmware / image package install
  sensors (Arduino-class) + DrakeVox triggers
  power management: stable SLS on external power + tablet battery policy
```

### TODO (tracked in project backlog)

1. **Clean the desktop before a firmware package install** — strip or replace default session chrome so the tablet boots to a field UI, not a full desktop playground.
2. **Tablet-oriented image or package** — repeatable install for field units (beyond user-local scripts).
3. **Sensor inputs** — MCU bridge into the same app.
4. **Power management** — keep Kinect + app stable on external supply; define tablet sleep/suspend policy so investigations are not interrupted.

## Related

- App: [../viewer/README.md](../viewer/README.md)
- Product vision: [../../../docs/PRODUCT-VISION.md](../../../docs/PRODUCT-VISION.md)
- Ubuntu / freenect: [UBUNTU-SETUP.md](UBUNTU-SETUP.md)
