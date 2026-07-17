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

1. **SLS core** — depth main + skeleton overlay (parity with Windows main view)  
2. **Appliance hardening** — auto-start kiosk, freenect udev, no gspca fights, watchdog restart  
3. **Image build** — documented image or scripted install for “load onto tablet”  
4. **Ovilus interface** — word/phrase display (timer and/or sensor-triggered); can share Kinect-derived events or MCU inputs  
5. **Additional sensors** — EMF, temp, IMU, etc. on Arduino (or similar); bridge into the same UI  
6. **Session tools** — light logging/recording when stable  

Spelling note: product/docs use **Ovilus** (spirit box–style word UI already referenced in Windows `AGENTS.md`).

## Hardware evolution

| Stage | Hardware |
|-------|----------|
| Now | Xbox 360 Kinect + host power/USB |
| Next | Tablet + Kinect integrated rig (photos/BOM in `hardware/`) |
| Later | Companion board (Arduino-class) for extra sensors + optional Ovilus triggers |
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
