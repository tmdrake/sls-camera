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

## Dependencies & version conflicts (issue tracking)

Report and resolve **apt/Python missing deps and package version conflicts** on the **sls-camera** issue tracker (not only in the firmware repo):

| Issue | Scope |
|-------|--------|
| [#2](https://github.com/tmdrake/sls-camera/issues/2) | Offline recursive deps, cache-based install path |
| [#3](https://github.com/tmdrake/sls-camera/issues/3) | OR-alternatives (`libjack`/`ffmpeg-extra`), python downgrades, new conflicts |

Sibling firmware docs point here: `sls-camera-firmware` → [OFFLINE-MIRROR.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/OFFLINE-MIRROR.md).

## Screenshots (appliance VM smoke test)

Phase 1 packaging was proven on a **Lubuntu 26.04** KVM guest with the sibling firmware installer; demo mode needs no Kinect.

| Desktop | SLS Camera (`--demo`) |
|---------|------------------------|
| ![Lubuntu desktop](images/01-guest-desktop.png) | ![SLS demo UI](images/02-sls-demo-app.png) |

See [`images/README.md`](images/README.md) for capture notes and a second HUD frame. Firmware first-boot notes: sibling repo `sls-camera-firmware` → `docs/FIRST-BOOT.md`.

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

## Tablet firmware (separate repo)

Dev install scripts above are for **developer hosts**. For a flashable / blow-and-go tablet image:

- **Repo:** `sls-camera-firmware` (sibling of this project: `~/sls-camera-firmware`)
- **Goals:** no-login kiosk, offline freenect + Python + MediaPipe cache, autostart SLS app, writable `/data/sls-captures`
- **Docs:** `sls-camera-firmware/README.md`, `docs/BUILD.md`, `docs/OFFLINE-MIRROR.md`
- **Phase 1:** `sudo ./scripts/install-appliance.sh` on a blank Ubuntu/Lubuntu tablet
- **Phase 2:** bootable ISO (not finished yet)

Do not put Microsoft Kinect UAC firmware in public firmware trees.

