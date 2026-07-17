# SLS Camera Project

Xbox 360 Kinect–based **SLS-style** depth + skeleton camera (Ghost Hunters–style stick figures), with a **working Linux field app** and a path toward a **tablet appliance** (Lubuntu-class image, optional Ovilus + extra sensors).

## Purpose

- Modified / field-portable **Xbox 360 Kinect** hardware  
- **Windows** SLS Explorer (Kinect SDK / WPF) — reference UI  
- **Linux** freenect + MediaPipe + **Qt fullscreen** viewer — **primary field app**  
- Future: Ovilus panel, Arduino-class sensors, flashable tablet image  

Product vision: [docs/PRODUCT-VISION.md](docs/PRODUCT-VISION.md).

## Structure

```text
analysis/           orientation & research notes
hardware/           schematics, wiring, photos, rig notes
docs/               shared project planning
software/
  docs/             Windows / shared code analysis
  source/           Windows WPF + Kinect sample-based app
  linux/            Ubuntu freenect + Qt SLS viewer
AGENTS.md           Windows app notes + Linux path pointer
```

## Software paths

| Path | Platform | Stack | Status |
|------|----------|--------|--------|
| [`software/source/`](software/source/) | Windows | Kinect SDK 1.x, WPF, .NET | Reference SLS Explorer code |
| [`software/linux/viewer/`](software/linux/viewer/) | Ubuntu / Lubuntu | freenect + MediaPipe + **Qt** | **Working field app** (2026-07) |

**Linux product goal (same as Windows main view):** colorized depth + SLS skeleton overlay — [plan](software/linux/docs/LINUX-SLS-PLAN.md).  
**UI:** Qt fullscreen always-on-top (optional `--ui web`).

### Linux app highlights

- Live depth + IR PiP, skeletons on colorized depth (max people 1–6, MediaPipe defaults via **Defaults**)  
- Spectrum strip (prefers **Kinect USB Audio** after `kinect-audio-setup`)  
- Main bar: **Settings · Snap · Record · Quit** (timestamped AVI **with mic audio**, REC elapsed)  
- Kinect disconnect → RECONNECTING screen + infinite retry; spectrum mic auto-retry  
- LED green + auto-level on open; IR sensor gain fixed at 50 (not in UI)  

Docs: [linux README](software/linux/README.md) · [viewer README](software/linux/viewer/README.md) · [Ubuntu setup](software/linux/docs/UBUNTU-SETUP.md) · [M0 bring-up](software/linux/notes/BRINGUP-FREENECT.md).

```bash
# Kinect depth check
./software/linux/scripts/check-kinect.sh

# Field app
cd software/linux/viewer && ./run.sh
```

## Delegation

- **Hardware Drake** — hardware review, schematics, add-ons, electrical feasibility  
- **Code Drake** — source, build, debugging, Windows and Linux implementation  
- **DrakeBot** — coordination and cross-domain planning  

## Next steps

1. ~~Linux M0 freenect / M1–M2 SLS UI~~  
2. ~~Spectrum + session Snap/Record~~  
3. ~~Mux audio into Record (AVI + mic)~~ · reconnect UI + mic retry  
4. ~~Dev install/uninstall scripts~~ · next: clean desktop → tablet firmware package  
5. Power management (external power + tablet) · sensors  
6. ~~Ovilus timer panel~~ · remaining: external triggers / sensor bridge  
6. Fill `hardware/` with portable-rig photos/wiring  
7. Windows app polish (Ovilus, installer) as needed  

Full backlog: [docs/TODO.md](docs/TODO.md).  

## License / firmware notes

Kinect **audio** UAC firmware is downloaded via `kinect-audio-setup` (Microsoft non-redistributable); not stored in this repo. See [UBUNTU-SETUP.md](software/linux/docs/UBUNTU-SETUP.md).
