# SLS Linux viewer

Fullscreen web app: **large colorized depth + skeleton**, **smaller IR + skeleton**.  
Operator is expected **behind the camera** (mirror **off** by default).

## Layout

| Pane | Content |
|------|---------|
| **Main (large)** | Colorized depth + SLS stick figures |
| **Side (small)** | Infrared camera + same stick figures |

Kinect 360 (libfreenect) cannot stream **RGB and IR at the same time**. This app runs **depth + IR** and runs MediaPipe pose on the **IR** image so both panes stay live.

## Quick start

```bash
# one-time: unload kernel webcam driver if needed
sudo modprobe -r gspca_kinect
# or: ../scripts/fix-kinect-access.sh

cd software/linux/viewer
./run.sh
```

Open **http://127.0.0.1:8765/** — tap once for fullscreen if the browser blocks auto-fullscreen.

Options:

```bash
./run.sh --demo          # synthetic frames if Kinect unavailable
./run.sh --mirror        # selfie-style flip (default off)
./run.sh --port 8765
```

## Stack

- `libfreenect` (system) via ctypes sync API  
- OpenCV — colorize, draw, JPEG  
- MediaPipe Tasks Pose Landmarker (`models/pose_landmarker_lite.task`)  
- Flask — MJPEG stream + minimal API  
- Web kiosk page — fullscreen, large touch buttons  

## Files

```text
viewer/
  run.sh
  requirements.txt
  models/pose_landmarker_lite.task   # auto-downloaded by run.sh
  sls_viewer/
    main.py          # Flask entry
    pipeline.py      # capture → pose → composite
    freenect_io.py   # ctypes freenect
    colorize.py
    pose.py
    skeleton.py
    config.py
  web/
    index.html
    style.css
    app.js
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| “gspca_kinect loaded” | `sudo modprobe -r gspca_kinect` + blacklist |
| open camera -3 | `../scripts/fix-kinect-access.sh` |
| No skeleton | Stand in IR/depth FOV ~1.5–3 m; room can be dark (IR illuminator) |
| Low FPS | `./run.sh` and set higher `pose_every_n_frames` in `config.py` |

Firmware / tablet image packaging is separate — see `docs/PRODUCT-VISION.md`.
