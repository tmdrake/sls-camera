# SLS Linux viewer

**Fullscreen native Qt app** (always on top): large **colorized depth + skeleton**, smaller **IR + skeleton**.  
Operator **behind the camera** — mirror **off** by default.

Browser kiosk is **optional** (`--ui web`), not the field UI.

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
| **Main (large)** | Colorized depth + SLS stick figures |
| **Side (small)** | Infrared + same stick figures |

Kinect streams **depth + IR** (not RGB+IR at once). Pose runs on **IR**.

## Quick start

```bash
sudo modprobe -r gspca_kinect   # if needed
cd software/linux/viewer
./run.sh
```

Keys: **Esc / Q** quit · **M** mirror · **F** re-assert fullscreen  
Touch: **Mirror** / **Quit** buttons on the bottom bar.

```bash
./run.sh --demo           # no Kinect (UI test)
./run.sh --mirror         # selfie flip
./run.sh --ui web         # optional browser UI on :8765
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
