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
- Later: audio spectrum, Ovilus-style word cues, session recording  

## Layers

```text
┌─────────────────────────────────────────────┐
│  Kiosk web UI (tablet / Lubuntu appliance)  │
│    depth+sticks · HUD · later Ovilus/sensors│
├─────────────────────────────────────────────┤
│  Python backend (systemd)  stream + control │
├─────────────────────────────────────────────┤
│  body / skeleton tracker                     │
│    primary: MediaPipe (or similar) on RGB    │
│    optional later: OpenNI + NiTE             │
├─────────────────────────────────────────────┤
│  libfreenect  (depth, RGB, IR, motor, LED)   │
├─────────────────────────────────────────────┤
│  USB  — Kinect 360 · future Arduino sensors  │
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

## Milestone sketch

1. **M0** — freenect install + `freenect-glview` — **done 2026-07-16**  
2. **M1** — backend live colorized depth (stream)  
3. **M2** — SLS stick figures on main depth view (**parity core**)  
4. **M3** — touch-friendly web kiosk chrome, tilt/mirror, HUD  
5. **M4** — tablet appliance image (auto-start)  
6. **M5** — Ovilus panel + Arduino/MCU sensor bridge  

Details and risks: [LINUX-SLS-PLAN.md](LINUX-SLS-PLAN.md).
