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

## UI decision (locked for planning)

**Product UI: local web UI in kiosk browser** (Chromium/Firefox fullscreen), fed by a **Python backend service**.

| Choice | Why |
|--------|-----|
| **Web kiosk** | Best default for **touch tablets**; easy dark SLS chrome; simple to add panels (Ovilus, sensors, status) |
| **Backend service** | freenect + pose + frame compose stay in Python; restartable via **systemd** on the image |
| **Not OpenCV highgui as product UI** | Fine for early spikes on the OptiPlex; poor touch/kiosk story |
| **Not primary Qt (for now)** | Lubuntu is LXQt-friendly, but web panels scale faster for Ovilus + multi-sensor dashboards; Qt remains a fallback if kiosk browser is too heavy on a given tablet |

**Dev path:** spike depth/pose on desktop (even OpenCV window) → same processing pipeline serves MJPEG/WebSocket into the kiosk UI → package as services on the image.

Detail: `software/linux/docs/LINUX-SLS-PLAN.md`.

## Software shape on the appliance

```text
┌─────────────────────────────────────────────────────────┐
│  Kiosk browser (fullscreen) — SLS page + Ovilus + HUD   │
├─────────────────────────────────────────────────────────┤
│  sls-backend  (systemd)  depth, pose, overlay, stream   │
│  optional: sensor-bridge  (USB/serial MQTT/HTTP)        │
├─────────────────────────────────────────────────────────┤
│  libfreenect · udev · blacklisted gspca · auto-login    │
├─────────────────────────────────────────────────────────┤
│  Tablet Linux image (Lubuntu/Ubuntu minimal + our pkgs) │
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
