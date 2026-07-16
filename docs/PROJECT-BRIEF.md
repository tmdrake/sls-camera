# PROJECT-BRIEF.md

## Project

SLS Camera

## Current understanding

SLS-style camera system based on an **Xbox 360 Kinect** (structured light depth + skeleton-style stick figures), with:

- Windows application under `software/source/` (Kinect SDK / WPF “SLS Explorer”)  
- Linux bring-up under `software/linux/` (libfreenect → web kiosk viewer → tablet image)  
- Possible future custom hardware add-ons under `hardware/`  
- Longer term: Ovilus UI + Arduino-class sensor packs (see `docs/PRODUCT-VISION.md`)  

Same physical sensor class used on Ghost Hunters–style “SLS camera” demos.

## Platforms

| Platform | Location | Primary goal | Status |
|----------|----------|--------------|--------|
| Windows | `software/source/` | Full SLS Explorer (depth, skeleton, Ovilus, spectrum) | Code in repo |
| Ubuntu / Lubuntu tablet | `software/linux/` | Depth + SLS sticks via **web kiosk** + backend; appliance image later | **M0 done**; UI + vision docs written |

## Planned ownership

- **DrakeBot:** intake, decomposition, coordination  
- **Hardware Drake:** schematics, electronics, camera hardware, add-ons  
- **Code Drake:** source code, app logic, tooling, Windows + Linux  

## Immediate needs

- [x] Software source in repo (`software/source/`)  
- [x] Linux path scaffold + Ubuntu setup notes  
- [x] freenect working on OptiPlex host (`freenect-glview`) — see `software/linux/notes/BRINGUP-FREENECT.md`  
- [x] Linux ↔ Windows UI parity plan — `software/linux/docs/LINUX-SLS-PLAN.md`  
- [x] Product vision + UI decision (web kiosk / tablet image) — `docs/PRODUCT-VISION.md`  
- [ ] Hardware photos / wiring notes in `hardware/`  
- [ ] Linux viewer M1 (backend depth stream)  
- [ ] Linux viewer M2 (skeleton overlay = usable SLS)  

## Definition of ready (updated)

Linux **M0** is complete. Product goal matches Windows main UI (depth + skeleton overlay) via MediaPipe-class pose + **web kiosk** UI for tablets. Appliance/Ovilus/sensor vision documented. Next session: implement M1/M2.