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
| **UI** | **None** — fixed in code; not shown in the status bar or Settings |
| **Processing** | Affects **IR PiP look only** — pose/skeletons use colorized depth, not IR gain |

## Spectrum strip

- Thin bar under the video (mic FFT).  
- Prefers **Kinect USB Audio** after `kinect-audio-setup` (see `docs/UBUNTU-SETUP.md`); else system default mic.  
- Needs system package: `sudo apt install libportaudio2` (for Python `sounddevice`).  
- Settings: **Spectrum** on/off.  

## Session tools (Settings)

| Action | Behavior |
|--------|----------|
| **Snapshot** | Save current composite JPEG under `viewer/captures/` |
| **Record** | Start/stop MJPG AVI of the composite view |
| **Auto-snap on detect** | Optional snap when `Detected` goes 0→≥1 |

## Skeletons / Settings

| Limit | Value |
|-------|--------|
| **Max people** | **1–6** — MediaPipe default **1**; Settings **Defaults** restores this |
| **Detected status** | `Detected:n/max` on the main status bar |
| **Confidence** | **0.25 – 0.99** — MediaPipe default **0.5** (detection/presence/tracking) |
| **Defaults button** | Resets Max=1 and Conf=0.5 (official MediaPipe PoseLandmarker options) |
| **Mirror** | in Settings |
| **Skeleton lines** | thin (1px bones, small joints) |

Sources: [PoseLandmarkerOptions](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarkerOptions) — `num_poses=1`, `min_pose_detection_confidence=0.5`, `min_pose_presence_confidence=0.5`, `min_tracking_confidence=0.5`.

Bottom bar: **Settings** · **Quit**. Spectrum strip sits above the bar when enabled.

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
