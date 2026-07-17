# PROJECT-BRIEF.md

## Project

SLS Camera

## Current understanding

SLS-style camera system based on an **Xbox 360 Kinect** (structured light depth + skeleton-style stick figures), with:

- Windows application under `software/source/` (Kinect SDK / WPF “SLS Explorer”)  
- **Working Linux field app** under `software/linux/viewer/` (libfreenect + MediaPipe + Qt)  
- Future: tablet image, Ovilus UI, Arduino-class sensor packs (`docs/PRODUCT-VISION.md`)  

Same physical sensor class used on Ghost Hunters–style “SLS camera” demos.

## Platforms

| Platform | Location | Primary goal | Status |
|----------|----------|--------------|--------|
| Windows | `software/source/` | Full SLS Explorer (depth, skeleton, Ovilus, spectrum) | Code in repo |
| Ubuntu / Lubuntu | `software/linux/viewer/` | Depth + SLS sticks, spectrum, session capture | **Field app working** (2026-07) |

## Linux field app (implemented)

- Qt fullscreen always-on-top; Settings popup  
- Live depth + IR PiP; skeletons on colorized depth  
- MediaPipe defaults (Conf 0.5, Max poses 1) via **Defaults** button  
- Spectrum (Kinect USB Audio after `kinect-audio-setup`)  
- Snap / Record on main bar (timestamped files, REC elapsed time)  
- Auto-level on open; no manual tilt UI; IR sensor gain fixed at 50 (hidden)  

Run: `cd software/linux/viewer && ./run.sh`

## Planned ownership

- **DrakeBot:** intake, decomposition, coordination  
- **Hardware Drake:** schematics, electronics, camera hardware, add-ons  
- **Code Drake:** source code, app logic, tooling, Windows + Linux  

## Immediate needs

- [x] Software source in repo (`software/source/`)  
- [x] Linux path scaffold + Ubuntu setup notes  
- [x] freenect working on OptiPlex (`freenect-glview`)  
- [x] Linux SLS viewer (depth + skeleton + IR PiP)  
- [x] Spectrum + session Snap/Record (video-only AVI)  
- [x] Kinect audio ALSA path documented (firmware / hash recovery)  
- [ ] **Mux audio into Record** (Kinect/system mic + video) — see `docs/TODO.md`  
- [ ] Hardware photos / wiring notes in `hardware/`  
- [ ] Tablet appliance image / autostart  
- [ ] Ovilus + sensor bridge  

Backlog: [docs/TODO.md](TODO.md).  

## Definition of ready (updated)

Linux field app is **usable for investigations** on a desktop host with Kinect. Remaining work is packaging (tablet image), Ovilus/sensors, and hardware BOM docs—not core SLS UI.
