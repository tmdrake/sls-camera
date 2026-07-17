# Linux SLS plan — parity with Windows UI

**Goal (same as Windows):** main screen = **depth-first view** with **SLS-style skeleton stick-figure overlay**.

**Answer:** **Yes, this can be done on Linux.** Depth is already proven (M0 / freenect). Skeleton tracking is **not** built into libfreenect; we add a body-pose layer and draw the same kind of stick figures the Windows Kinect SDK provides.

Reference Windows UI: `software/source/example/KinectWindow.xaml` — depth viewer + `KinectSkeletonViewer` stacked on top (`ShowBones`, `ShowJoints`, `ImageType="Depth"`). Product notes: root `AGENTS.md`.

**Longer product vision** (tablet image, sensors, Ovilus): `docs/PRODUCT-VISION.md`.

---

## UI decision (updated)

| Layer | Decision |
|-------|----------|
| **Product / tablet UI** | **Qt (PySide6) fullscreen + always-on-top** — primary field app |
| **Processing** | Same process: freenect + pose + composite pipeline thread |
| **Optional** | `--ui web` browser/MJPEG for remote glance or experiments |
| **Why Qt over browser kiosk** | True fullscreen + `WindowStaysOnTopHint`; no browser gesture/flags dance; better “appliance app” feel on Lubuntu tablets |
| **Ovilus / sensors later** | Qt panels or a second window; web remains available if we want HTML dashboards |

Target field OS: **Lubuntu / Ubuntu-class** tablet image with auto-login + **autostart Qt SLS app**. Large touch buttons + keyboard fallback (Esc/Q/M/F).

---

## What “same as Windows” means (v1 parity)

Must-have for **Linux SLS v1** (matches the main Ghost Hunters look):

| Feature | Windows today | Linux target |
|---------|---------------|--------------|
| Main view is **depth** (colorized) | Yes | Yes |
| **Skeleton overlay** on main view (bones + joints) | Kinect SDK skeleton stream | Pose tracker → stick figure |
| Dark “paranormal” frame / chrome | Theme in WPF | Dark **web** chrome (kiosk) |
| Un-mirrored option (operator behind camera) | Yes | Toggle (touch + key) |
| Runs on this OptiPlex + Kinect 360 | N/A (Windows box) | Ubuntu + freenect |
| Tablet / appliance image | N/A | Lubuntu-class image + systemd services |

Nice-to-have for **v1.x** (Windows already notes these; not required for first usable SLS screen):

| Feature | Priority |
|---------|----------|
| Side / swap color view | Medium |
| Motor tilt controls | Done (auto-level only; no manual UI) |
| Spectrum analyser under main view | **Done** |
| Session record (AVI + mic) | **Done** |
| Reconnect / mic retry | **Done** |
| Ovilus random words (5–15 min, timestamped) | **Done** (timer; external triggers later) |

---

## Feasibility

```text
Windows:  Kinect USB → Microsoft Kinect SDK 1.x → depth frame + skeleton joints → WPF overlay
Linux:    Kinect USB → libfreenect → depth + RGB frames → pose engine → draw sticks on depth → window
```

| Piece | On Linux? | Notes |
|-------|-----------|--------|
| Depth + RGB + motor | **Yes** | freenect (M0 done) |
| Classic Kinect SDK skeleton | **No** (SDK is Windows-only) | Same *look* via another pose source |
| Stick figures on depth | **Yes** | Draw bones between joints in image space |
| Full WPF clone | Not required | Match **layout and behavior**, not the .NET framework |

So: **same operator experience is realistic.** Joint source may differ from Microsoft’s tracker; the on-screen SLS look is still achievable.

---

## Skeleton / pose options (decision)

| Option | How it works | Pros | Cons | Recommendation |
|--------|--------------|------|------|----------------|
| **A. MediaPipe Pose (or similar) on RGB** | Estimate body landmarks on color frame; map/draw onto depth view | Maintained, Python-friendly, good stick figures | Not official Kinect joints; RGB↔depth alignment needed | **Primary path** |
| **B. OpenNI + NiTE** | Legacy Kinect skeleton middleware | Closest to classic Kinect skeletons | Old, closed NiTE, fragile on Ubuntu 26.04 | Fallback only if A is not “Kinect-like” enough |
| **C. Depth-only custom clustering** | Segment depth blobs, invent a stick figure | No RGB needed | Hard, flaky, lots of R&D | Research only |
| **D. Run Windows app in VM** | Passthrough USB to Windows | Pixel-perfect existing app | Not a Linux product path | Out of scope for `software/linux/` |

**Decision for planning:** pursue **Option A** for Linux SLS v1. Document NiTE as optional experiment, not a blocker.

### Alignment note (RGB pose → depth overlay)

MediaPipe runs on **color**. Windows skeleton is in **depth** image space. Plan:

1. Grab freenect **depth** and **RGB** each frame (registered if available; freenect has depth→RGB registration helpers / approximate scale).
2. Run pose on RGB (optionally downscaled for FPS).
3. Project landmarks into the depth view coordinate system (scale/crop to match depth resolution, or use freenect registration).
4. Draw green/cyan bones + joints on the depth image (SLS look).
5. Show that composite as the **main** window.

If registration is imperfect at first, v1 can draw sticks on a dual layout (depth main + thin RGB) or on RGB with depth false-color blend — still “SLS-like” for field use — then tighten alignment.

---

## Proposed Linux stack

```text
┌──────────────────────────────────────────────────────────┐
│  Kiosk browser — SLS page (depth+sticks), HUD, later       │
│    Ovilus panel + sensor tiles (touch-friendly)            │
├──────────────────────────────────────────────────────────┤
│  HTTP / WebSocket / MJPEG  (local only, e.g. 127.0.0.1)  │
├──────────────────────────────────────────────────────────┤
│  backend service (systemd on appliance)                    │
│    skeleton.py  — landmarks → bones → draw on depth        │
│    pose.py      — MediaPipe (or swap-in backend)           │
│    depth.py     — freenect frames, colorize, register      │
│    stream.py    — serve composite + control API            │
├──────────────────────────────────────────────────────────┤
│  libfreenect (+ Python bindings)                           │
│  future: sensor-bridge ← Arduino / MCU (USB serial)        │
└──────────────────────────────────────────────────────────┘
```

**Language:** Python 3 for backend + static/simple web frontend. Revisit C++ only if FPS forces it.

**Bindings:** prefer packaged/python freenect if available; else libfreenect wrappers. Spike this in M1.

**Ovilus + extra sensors:** same web shell; Ovilus as a panel/API; Arduino-class boards as a separate bridge process publishing into the UI (not blocking SLS core).

---

## Milestones (updated 2026-07)

| ID | Deliverable | Success criteria | Status |
|----|-------------|------------------|--------|
| **M0** | freenect on host | `freenect-glview` live video | **Done** |
| **M1** | Depth main window | Live colorized depth, mirror, ~15+ FPS | **Done** (`viewer/`) |
| **M2** | SLS skeleton overlay | Sticks on depth (+ IR PiP) | **Done** (MediaPipe on colorized depth) |
| **M3** | Field UI polish | Qt Settings, spectrum, Snap/Record+audio, reconnect | **Done** (auto-level only; no manual tilt) |
| **M4** | Appliance image | Auto-start on Lubuntu-class tablet | Not started |
| **M5a** | Ovilus panel | 5–15 min timestamped words on Qt UI | **Done** (timer; triggers later) |
| **M5b** | Sensors | Arduino/MCU bridge + Ovilus triggers | Not started |

**Definition of “Linux SLS usable”:** M2 — **met** on OptiPlex + Kinect.

**Definition of “field appliance alpha”:** M4 — tablet boots to SLS without manual SSH.

---

## Windows feature map → Linux work

| Windows (`AGENTS.md` / KinectWindow) | Linux | Status |
|--------------------------------------|-------|--------|
| Depth stream main | `pipeline` + `colorize` | Done |
| Skeleton bones/joints on depth | `pose` + `skeleton` | Done |
| Un-mirrored for behind-camera | Settings mirror (default off) | Done |
| IR secondary view | top-right PiP | Done |
| Spectrum analyser | `spectrum.py` + Kinect USB Audio + mic retry | Done |
| Session capture | Snap / Record main bar; AVI + PCM mic | Done |
| Device reconnect | RECONNECTING UI; infinite freenect retry | Done |
| Tilt control | Auto-level on open only | Done (no manual UI by design) |
| Ovilus 5–15 min + timestamp | `ovilus.py` + Settings / key O | Done (timer) |
| Color side / swap | — | Optional later |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Python freenect bindings missing on 26.04 | Spike early; fall back to ctypes or thin C helper |
| Pose FPS too low on CPU | Downscale RGB for pose; run pose every Nth frame; stick with last skeleton |
| RGB/depth misalignment | freenect registration; calibration constants; accept “good enough” for v1 |
| False sticks (noise) | confidence threshold; min joint count; optional “skeleton only if standing volume in depth” |
| gspca fights freenect again | Keep blacklist + fix script; document in UBUNTU-SETUP |

---

## Repo layout (viewer / appliance implementation)

```text
software/linux/viewer/
  README.md
  requirements.txt
  run.sh                 # dev: backend + open browser
  sls_viewer/
    main.py              # service entry
    depth.py
    pose.py
    skeleton.py
    stream.py            # MJPEG / WebSocket / control API
    config.py
  web/                   # kiosk frontend (SLS page, later Ovilus)
    index.html
    app.js
    style.css
```

Shared product goals: root `AGENTS.md`, `docs/PRODUCT-VISION.md`, this plan.

---

## Open questions (resolve during M1–M4)

1. **Pose backend:** MediaPipe vs lighter model if tablet CPU is weak.  
2. **Tablet model / Lubuntu version** for the golden image.  
3. **Default mirror:** un-mirrored for behind-camera — default **on**.  
4. **Multi-person:** v1 one strongest pose; multi later.  
5. **Ovilus trigger sources:** timer only first; then depth/skeleton events; then Arduino sensors.  

Defaults locked: **MediaPipe + web kiosk UI + Python backend + unmirrored default + single person first.**

---

## Immediate next engineering steps

1. Spike: freenect depth frames into Python/NumPy on OptiPlex.  
2. M1: backend serves colorized depth (even if UI is temporary).  
3. M2: MediaPipe sticks on composite + main web view.  
4. Field/tablet test; note FPS and false positives.  
5. M3/M4 kiosk + image; then Ovilus/sensor bridge.

---

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — stack layers  
- [UBUNTU-SETUP.md](UBUNTU-SETUP.md) — host install  
- [../notes/BRINGUP-FREENECT.md](../notes/BRINGUP-FREENECT.md) — M0 log  
- Root [AGENTS.md](../../../AGENTS.md) — product features  
- Windows UI: `software/source/example/KinectWindow.xaml`  
