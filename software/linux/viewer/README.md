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
4. Set **IR sensor brightness to 50/50** (freenect max useful gain; library default is ~30).  
   Note: this is **sensor gain**, not IR projector power (projector stays on for depth).  
5. Stream live depth (main) + IR (PiP); draw skeletons when pose detects a person  

**Skeletons:** pose runs on **colorized depth only**, max **2** people. Status shows `Detected:#`. Stand ~1.5–3 m in the depth FOV.

**IR brightness:** bottom bar `IR −` / `IR +` (1–50, sensor gain). Saved in `user_settings.json` and restored next run. Keys: `[` `]` (±5), `-` `=` (±1).  

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
