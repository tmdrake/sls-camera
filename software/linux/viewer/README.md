# SLS Linux viewer

**Fullscreen native Qt app** (always on top):

- **Main:** full-screen **colorized depth + skeleton**
- **PiP:** small **IR + skeleton** in the **top corner** (scaled)
- **Mirror OFF by default** (toggle in Settings or `--mirror`)

Browser UI is **optional** (`--ui web`).

## Why Qt (not browser kiosk)

| | Qt (default) | Browser kiosk |
|--|--------------|---------------|
| Fullscreen | `showFullScreen()` | Needs flags / user gesture |
| Always on top | `WindowStaysOnTopHint` | Unreliable across WMs |
| Tablet / Lubuntu field use | **Yes** | Possible, more fragile |

## Layout

| Pane | Content |
|------|---------|
| **Full frame** | Colorized depth + SLS stick figures |
| **Top-corner PiP** | Infrared + same stick figures (small, scaled) |

Kinect streams **depth + IR** (not RGB+IR at once). Pose runs on **colorized depth**.

## Quick start (live Kinect)

```bash
# if freenect says BUSY / cannot open:
sudo modprobe -r gspca_kinect
# or: ../scripts/fix-kinect-access.sh

cd software/linux/viewer
./run.sh
```

On open the app will:

1. Claim the Kinect (depth + IR)  
2. Set the **LED to green**  
3. **Auto-level** the tilt motor to **0°**  
4. Set **IR sensor gain to 50** (full freenect range; fixed, not in UI)  
5. Stream live depth (main) + IR (PiP); skeletons from colorized-depth pose  

## IR sensor gain (fixed)

| Item | Detail |
|------|--------|
| **Value** | **50** (full; freenect range is 1–50) |
| **What it is** | IR **camera sensor gain** only |
| **What it is not** | IR **projector** power (projector stays on for depth; not software-adjustable here) |
| **UI** | **None** — fixed at 50; noted in Settings as read-only text |
| **Processing** | Affects **IR PiP look only** — pose/skeletons use colorized depth, not IR gain |

Status bar shows `IR gain 50` when live.

## Skeletons / Settings

| Limit | Value |
|-------|--------|
| **Max people** | **1–6** (default **4**) — in **Settings** |
| **Detected status** | `Detected:n/max` on the main status bar |
| **Confidence** | **0.25 – 0.99** (default 0.70) — in Settings |
| **Mirror** | in Settings |
| **Skeleton lines** | thin (1px bones, small joints) |

Bottom bar: **Settings** · **Quit**.  

Keys: `S` settings · `[` `]` conf · `,` `.` max people · `M` mirror · `Esc` closes Settings then quits · `F` fullscreen · `Q` quit.

```bash
./run.sh --demo            # synthetic UI test (no Kinect)
./run.sh --mirror          # horizontal mirror on
./run.sh --no-auto-level   # leave tilt where it is
./run.sh --led-off         # no green LED
./run.sh --ui web          # optional browser UI
```

## Stack

- **PySide6** — fullscreen always-on-top window  
- `libfreenect` via ctypes  
- OpenCV — colorize, draw, composite  
- MediaPipe Pose Landmarker  
- Flask — only if `--ui web`  

## Files

```text
viewer/
  run.sh
  sls_viewer/
    main.py          # entry (--ui qt|web)
    qt_app.py        # fullscreen UI + Settings popup
    pipeline.py      # capture → pose → composite
    freenect_io.py
    ...
  web/               # optional browser UI
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Window not on top | Press **F** |
| gspca / open failed | `sudo modprobe -r gspca_kinect` + fix script |
| Black window | Wait for first frame; try `./run.sh --demo` |
| No DISPLAY | Need a desktop session |

Firmware / tablet image packaging is separate — see `docs/PRODUCT-VISION.md`.
