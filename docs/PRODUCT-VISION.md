# Product vision — field SLS appliance

## End goal

A **bulletproof Linux image** you flash onto tablets (or small PCs) that ship with the **hardware already built** (Kinect / SLS head unit + power + cabling). Operator turns it on and gets a Ghost Hunters–style **depth + skeleton** main screen, with room to grow into multi-sensor investigation gear.

Not a one-off laptop hack — a **repeatable appliance** (firmware-like image + fixed hardware BOM).

## Platforms

| Platform | Role |
|----------|------|
| **Windows** (`software/source/`) | Reference SLS Explorer (Kinect SDK, full desktop app) |
| **Linux appliance** (`software/linux/`) | Field image for tablets / Lubuntu (or similar) |
| **Dev host** (e.g. OptiPlex) | Bring-up, freenect M0, implement services before imaging tablets |

## Target form factor

- Tablet (touch) or small panel PC running **Lubuntu / Ubuntu** (or a locked-down derivative)
- Pre-integrated Kinect 360 (or same class depth sensor)
- Optional external power path already designed into the rig
- Future: more sensors on the same device or a companion MCU

Touch may be imperfect on some tablets; UI must still work with **large controls**, **fullscreen kiosk**, and **keyboard/remote** fallback.

## UI decision (locked)

**Product UI: Qt (PySide6) native window — fullscreen and always-on-top.**

| Choice | Why |
|--------|-----|
| **Qt fullscreen + always on top** | Reliable field app: covers the desktop, stays visible, works on Lubuntu/tablets without browser quirks |
| **Same Python process** | freenect + pose + composite in a background thread; UI only displays frames |
| **Optional web UI** | `--ui web` for debug/remote; not required for the appliance |
| **Not browser kiosk as primary** | Auto-fullscreen and always-on-top are fragile across browsers/WMs |

**Appliance path:** autostart `./run.sh` (or systemd user unit) after login → Qt SLS fills the screen.

Detail: `software/linux/docs/LINUX-SLS-PLAN.md` · app: `software/linux/viewer/`.

## Software shape on the appliance

```text
┌─────────────────────────────────────────────────────────┐
│  Qt SLS app — fullscreen, always-on-top                 │
│    depth+skeleton main · IR+skeleton side · HUD         │
├─────────────────────────────────────────────────────────┤
│  Python pipeline (same process / systemd)               │
│  optional: sensor-bridge  (USB/serial)                  │
├─────────────────────────────────────────────────────────┤
│  libfreenect · udev · blacklisted gspca · auto-login    │
├─────────────────────────────────────────────────────────┤
│  Tablet Linux image (Lubuntu/Ubuntu + our app)          │
└─────────────────────────────────────────────────────────┘
         │ USB                  │ USB/serial (future)
         ▼                      ▼
      Kinect 360            Arduino / MCU sensor pack
```

## Feature roadmap (product)

1. **SLS core** — depth main + skeleton overlay — **done on Linux** (`software/linux/viewer/`)  
2. **Session tools** — Snap / Record (AVI + mic) / detect auto-snap — **done on Linux**  
3. **Spectrum** — mic FFT strip (Kinect UAC after `kinect-audio-setup`) — **done on Linux**  
4. **Field resilience** — Kinect reconnect UI + mic retry — **done on Linux**  
5. **Dev packaging** — install/uninstall scripts for launcher + optional autostart — **done** (`software/linux/scripts/install-field-app.sh`)  
6. **Appliance hardening** — freenect udev, no gspca fights, watchdog restart; **clean desktop before firmware package**  
7. **Image / firmware package** — tablet-oriented install (not just `~/.local` wrappers)  
8. **DrakeVox interface** — word/phrase display + TTS — **done on Linux** (not “Ovilus”; trademark-safe name); sensor triggers later  
9. **Additional sensors** — EMF, temp, IMU, etc. on Arduino (or similar); bridge into the same UI  
10. **Power management** — stable SLS on **external power** + tablet (sleep/USB policy so investigations stay up)  

Naming: Linux field app uses **DrakeVox** (spirit-box style words + TTS). Older Windows code may still say Ovilus.

## Hardware evolution

| Stage | Hardware |
|-------|----------|
| Now | Xbox 360 Kinect + host power/USB |
| Next | Tablet + Kinect integrated rig (photos/BOM in `hardware/`) |
| Later | Companion board (Arduino-class) for extra sensors + optional DrakeVox triggers |
| Optional | Custom carrier / power / tilt — still under `hardware/` |

## Success criteria (long term)

- Flash/install image on a prepared tablet → boot → SLS screen without SSH  
- Same software tree works on OptiPlex for development  
- Windows app remains the behavioral reference where useful  
- New sensors appear as modules in the UI, not a second disconnected app  

## Related docs

- Linux plan: `software/linux/docs/LINUX-SLS-PLAN.md`  
- Ubuntu bring-up: `software/linux/docs/UBUNTU-SETUP.md`  
- M0 log: `software/linux/notes/BRINGUP-FREENECT.md`  
- Windows app notes: `AGENTS.md`  
