# Linux SLS path

Ubuntu / freenect path for the same Xbox 360 Kinect (NUI) hardware used by the Windows SLS Explorer under `software/source/`.

## Status (2026-07)

| Milestone | Status |
|-----------|--------|
| **M0** — freenect install + `freenect-glview` | **Done** (OptiPlex + Kinect 360) |
| **M1+M2** — depth + skeleton field UI | **Done** — Qt app under `viewer/` |
| **Spectrum** — mic FFT strip | **Done** (Kinect USB Audio preferred after firmware) |
| **Session** — Snap / Record + mic in AVI | **Done** (main bar + Settings) |
| **Reconnect** — video + mic retry | **Done** (RECONNECTING UI; spectrum mic retry) |
| **Dev install / uninstall scripts** | **Done** (`scripts/install-field-app.sh`) |
| **Offline-safe apt seeds (#2)** | **Done** (`install-apt-deps.sh` + `packages/apt-packages.txt`) |
| **Tablet firmware image** | Sibling `sls-camera-firmware` (see [FOR-FIRMWARE-TEAM.md](docs/FOR-FIRMWARE-TEAM.md)) |
| **DrakeVox** word panel (5–15 min, timestamped) | **Done** |
| **Arduino sensors + DrakeVox triggers** | Not started |
| **External power policy** | Not started |

- Bring-up: [notes/BRINGUP-FREENECT.md](notes/BRINGUP-FREENECT.md)  
- Parity plan: [docs/LINUX-SLS-PLAN.md](docs/LINUX-SLS-PLAN.md)  
- Product vision: [../../docs/PRODUCT-VISION.md](../../docs/PRODUCT-VISION.md)  
- **Field app:** [viewer/README.md](viewer/README.md) · `viewer/run.sh`  

## Goal

**Same as the Windows UI:** main screen = depth feed with **SLS skeleton stick-figure overlay**.

| Feature | Status |
|---------|--------|
| Live depth + IR PiP | Done |
| Stick figures (MediaPipe on colorized depth) | Done |
| Spectrum strip | Done |
| Snap / Record (AVI + mic audio) | Done |
| Kinect reconnect + mic retry | Done |
| Auto-level tilt (no manual tilt UI) | Done |
| DrakeVox / multi-sensor | Later |

## Layout

```text
software/linux/
  README.md
  docs/
    UBUNTU-SETUP.md         # freenect, gspca, Kinect audio firmware
    FIELD-INSTALL.md        # install/uninstall + tablet roadmap
    ARCHITECTURE.md
    LINUX-SLS-PLAN.md
  scripts/
    check-kinect.sh         # USB, freenect, ALSA Kinect mic
    install-freenect.sh
    fix-kinect-access.sh
    install-field-app.sh    # dev packaging: launcher + optional autostart
    uninstall-field-app.sh
  viewer/                   # Qt SLS application
    run.sh
    README.md
    sls_viewer/
    captures/               # local snaps/recordings (gitignored)
  notes/
    MACHINE-STATUS.md
    BRINGUP-FREENECT.md
```

## Quick start

```bash
# from repo root
./software/linux/scripts/check-kinect.sh

cd software/linux/viewer
./run.sh
./run.sh --help    # all flags; --demo is freenect-open fallback only
```

Main bar: **Settings · Snap · Record · Quit**.  
Keys: `S` settings · `C` snap · `R` record · `O` DrakeVox · `F` fullscreen · `Q` quit.  

Full CLI / `--demo` / PortAudio preflight: [viewer/README.md](viewer/README.md#cli-runsh).

### Dev packaging (launcher / autostart)

```bash
# optional: menu launcher + login autostart (points at this clone)
./software/linux/scripts/install-field-app.sh
# daily dev without autostart:
./software/linux/scripts/install-field-app.sh --no-autostart
./software/linux/scripts/uninstall-field-app.sh

# details + tablet / firmware TODO:
#   software/linux/docs/FIELD-INSTALL.md
```

If freenect fails (`BUSY` / open -3):

```bash
sudo modprobe -r gspca_kinect
./software/linux/scripts/fix-kinect-access.sh
```

Kinect **mic** for spectrum: install `kinect-audio-setup` + `libportaudio2` (see [UBUNTU-SETUP.md](docs/UBUNTU-SETUP.md)). Hash-mismatch recovery for the SDK MSI is documented there.

Full freenect install: [docs/UBUNTU-SETUP.md](docs/UBUNTU-SETUP.md).

## Relation to Windows code

| Path | Role |
|------|------|
| `software/source/` | Windows WPF + Kinect SDK 1.x (reference SLS Explorer) |
| `software/linux/viewer/` | Field Linux app |
| `hardware/` | Shared camera mod / power / wiring notes |
| `docs/` | Cross-platform project brief |

Do **not** split into a separate product repo unless the Linux app ships alone later.
