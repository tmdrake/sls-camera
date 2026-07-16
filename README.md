# SLS Camera Project

Xbox 360 Kinect–based **SLS-style** depth + skeleton camera work (Ghost Hunters–style stick figures), plus a path toward a **tablet Linux appliance** (Lubuntu-class image, kiosk UI, optional Ovilus + extra sensors).

## Purpose

- Modified / field-portable **Xbox 360 Kinect** hardware  
- **Windows** SLS Explorer app (Kinect SDK / WPF)  
- **Linux** freenect + **web kiosk** viewer (tablet / Lubuntu appliance)  
- Future: Ovilus panel, Arduino-class sensor packs  
- Shared analysis, hardware docs, and planning  

Product vision: [docs/PRODUCT-VISION.md](docs/PRODUCT-VISION.md).  

## Structure

```text
analysis/           orientation & research notes
hardware/           schematics, wiring, photos, rig notes
docs/               shared project planning
software/
  docs/             Windows / shared code analysis
  source/           Windows WPF + Kinect sample-based app
  linux/            Ubuntu freenect path + planned viewer
AGENTS.md           app features / build notes (Windows-focused; Linux mirrors goals)
```

## Software paths

| Path | Platform | Stack | Status |
|------|----------|--------|--------|
| [`software/source/`](software/source/) | Windows | Kinect SDK 1.x, WPF, .NET | Existing SLS Explorer code |
| [`software/linux/`](software/linux/) | Ubuntu / Lubuntu tablet | freenect + pose + **web kiosk** | **M0 done**; UI + appliance plan written |

**Linux product goal (same as Windows):** main depth screen + SLS skeleton overlay — [plan](software/linux/docs/LINUX-SLS-PLAN.md).  
**UI decision:** kiosk **web UI** + Python backend (not OpenCV as field UI).

Start on Linux: [software/linux/README.md](software/linux/README.md) · [setup](software/linux/docs/UBUNTU-SETUP.md) · [M0 bring-up](software/linux/notes/BRINGUP-FREENECT.md).

```bash
./software/linux/scripts/check-kinect.sh
freenect-glview
```

## Delegation

- **Hardware Drake** — hardware review, schematics, add-ons, electrical feasibility  
- **Code Drake** — source, build, debugging, Windows and Linux implementation  
- **DrakeBot** — coordination and cross-domain planning  

## Next steps

1. ~~Scaffold Linux layout on Ubuntu host~~  
2. ~~Install freenect, blacklist `gspca_kinect`, run `freenect-glview`~~ (**M0 complete**, 2026-07-16)  
3. Linux **M1/M2**: depth main window + SLS skeleton overlay ([plan](software/linux/docs/LINUX-SLS-PLAN.md))  
4. Fill `hardware/` with photos/wiring for the portable rig  
5. Continue Windows app polish (spectrum, Ovilus triggers, installer) per `AGENTS.md`  
