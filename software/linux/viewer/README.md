# SLS Linux viewer

**Fullscreen native Qt app** (always on top):

- **Main:** full-screen **colorized depth + skeleton**
- **PiP:** small **IR + skeleton** in the **top corner** (scaled)
- **Mirror OFF by default** (toggle in UI or `--mirror`)

Browser UI is **optional** (`--ui web`).

## Why Qt (not browser kiosk)

| | Qt (default) | Browser kiosk |
|--|--------------|---------------|
| Fullscreen | `showFullScreen()` | Needs flags / user gesture |
| Always on top | `WindowStaysOnTopHint` | Unreliable across WMs |
| Tablet / Lubuntu field use | **Yes** | Possible, more fragile |
| Extra sensor panels later | Still fine (or hybrid) | Easier HTML dashboards |

For a bulletproof “this is the app” experience: **Qt fullscreen always-on-top**.

## Layout

| Pane | Content |
|------|---------|
| **Full frame** | Colorized depth + SLS stick figures |
| **Top-corner PiP** | Infrared + same stick figures (small, scaled) |

Kinect streams **depth + IR** (not RGB+IR at once). Pose runs on **IR**.

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
4. Set **IR sensor brightness fixed at 50/50** (no UI control for now)  
5. Stream live depth (main) + IR (PiP); skeletons from **colorized depth** pose (max 2)  

**Skeletons:** colorized-depth pose only.

| Limit | Value |
|-------|--------|
| **Max people** | **1–6** (default **4**) — in **Settings** popup |
| **Detected status** | `Detected:n/max` on the main status bar |
| **Confidence** | **0.25 – 0.99** (default 0.70) — in Settings |
| **Mirror** | in Settings |
| **Skeleton lines** | thin (1px bones, small joints) |

Bottom bar: **Settings** · **Quit**. Open Settings for Max / Conf / **IR brightness** / Mirror.  
Keys: `S` settings · `[` `]` conf · `,` `.` max · `-` `=` IR · `M` mirror · `Esc` closes Settings then quits.  

IR control is **sensor gain** (1–50), not projector power; default **50**, saved with other prefs.  

Keys: **Esc / Q** quit · **M** mirror · **F** re-assert fullscreen  

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
    qt_app.py        # fullscreen always-on-top UI
    pipeline.py      # capture → pose → composite
    freenect_io.py
    ...
  web/               # optional browser UI
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Window not on top | Press **F**; some WMs need “focus follows” off |
| gspca / open failed | `sudo modprobe -r gspca_kinect` + fix script |
| Black window | Wait for first frame; try `./run.sh --demo` |
| No DISPLAY | Need a desktop session (not pure SSH without X) |
