# Linux architecture sketch

## Product goal (parity with Windows)

**Same as Windows SLS Explorer main screen:** depth-first view with **skeleton stick-figure overlay** (Ghost Hunters–style SLS look).

Windows: Kinect SDK 1.x skeleton stream + WPF (`software/source/example/KinectWindow.xaml`).  
Linux: freenect depth/RGB + pose engine + drawn overlay (`software/linux/viewer/`).

Full plan: [LINUX-SLS-PLAN.md](LINUX-SLS-PLAN.md).

Shared look (from root `AGENTS.md`):

- Dark UI  
- **Depth-first** main view  
- **Skeleton stick figures** over depth  
- Optional secondary color view  
- Un-mirrored option for operator behind camera  
- Spectrum strip + session Snap/Record (AVI + mic) — **done on Linux**  
- Ovilus random words (5–15 min, timestamped) — **done on Linux**  
- Later: Ovilus external triggers, extra sensors  

## Layers

```text
┌─────────────────────────────────────────────┐
│  Qt field UI (fullscreen) · optional web UI │
│    depth+sticks · spectrum · snap/record    │
│    reconnect · later Ovilus / sensors       │
├─────────────────────────────────────────────┤
│  Python pipeline (thread) + session_io      │
│    MediaPipe pose on colorized depth        │
│    sounddevice mic · ffmpeg AVI mux         │
├─────────────────────────────────────────────┤
│  libfreenect  (depth, IR, motor, LED)       │
│  Kinect USB Audio (UAC after firmware)      │
├─────────────────────────────────────────────┤
│  USB  — Kinect 360 · future Arduino sensors │
└─────────────────────────────────────────────┘
```

UI decision and appliance vision: [LINUX-SLS-PLAN.md](LINUX-SLS-PLAN.md), `docs/PRODUCT-VISION.md`.

## Why freenect first

- Packaged on Ubuntu (`freenect`, `libfreenect-bin`)
- Works with **Xbox 360** Kinect IDs on this machine (M0 proven)
- Proves depth + tilt before investing in skeleton UI
- Avoids blocking on NiTE for the first usable SLS screen

## Skeleton decision

| Option | Role |
|--------|------|
| **MediaPipe / modern pose on RGB** | **Primary** — draw SLS sticks on depth main view |
| **OpenNI + NiTE** | Optional if classic Kinect joints are mandatory |
| **Port Windows joint drawing only** | Reuse bone connectivity ideas; joints still need a Linux source |

libfreenect does **not** include Microsoft-style skeleton tracking. Overlay is application-layer (same visual goal, different joint source).

## What stays out of `software/linux/`

- Windows WPF projects stay in `software/source/`
- Shared hardware photos/schematics go under `hardware/`
- Cross-cutting goals stay in `docs/` and root `README.md` / `AGENTS.md`

## Milestone status (2026-07)

1. **M0** — freenect install + `freenect-glview` — **done**  
2. **M1** — live colorized depth in app — **done**  
3. **M2** — SLS stick figures on depth + IR PiP — **done**  
4. **M3** — Qt Settings, spectrum, Snap/Record+audio, reconnect — **done**  
5. **M4** — tablet appliance image — **not started**  
6. **M5a** — Ovilus timer panel — **done**  
7. **M5b** — Arduino/MCU + Ovilus triggers — **not started**  

Field app: `software/linux/viewer/`. Details: [LINUX-SLS-PLAN.md](LINUX-SLS-PLAN.md).
