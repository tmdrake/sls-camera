# SLS Linux viewer

**Fullscreen native Qt app** (always on top) for Xbox 360 Kinect SLS-style monitoring.

## Features (current)

| Area | Behavior |
|------|----------|
| **Main view** | Full-screen **colorized depth + skeleton** |
| **PiP** | Small **IR + skeleton** (top-right) |
| **Pose** | MediaPipe on **colorized depth** only |
| **Spectrum** | FFT strip under video; prefers **Kinect USB Audio** |
| **Snap** | Timestamped JPEG → `captures/sls_YYYYMMDD_HHMMSS.jpg` |
| **Record** | Timestamped AVI (**video only** — no mic yet); **elapsed** (`REC 0:12`). A/V mux: [docs/TODO.md](../../../docs/TODO.md) |
| **Settings** | Max people, confidence, mirror, spectrum, auto-snap, Defaults |
| **On open** | LED green, tilt auto-level 0°, IR sensor gain **50** (fixed, not in UI) |

Browser UI is optional (`--ui web`).

## Quick start

```bash
# if freenect says BUSY / cannot open:
sudo modprobe -r gspca_kinect
# or: ../scripts/fix-kinect-access.sh

cd software/linux/viewer
./run.sh
```

### Packages (host)

```bash
sudo apt install -y freenect libfreenect-bin libportaudio2 alsa-utils
# Kinect mic for spectrum (one-time; MS firmware download — see docs):
sudo apt install -y kinect-audio-setup
# unplug/replug Kinect; arecord -l should list "Kinect USB Audio"
```

If `kinect_fetch_fw` fails with **Invalid hash**, see [UBUNTU-SETUP.md](../docs/UBUNTU-SETUP.md) recovery steps.

## Main bar

**Settings · Snap · Record · Quit**

| Control | Action |
|---------|--------|
| **Snap** | Save current composite frame |
| **Record** | Start/stop recording; button becomes `Stop M:SS` |
| **Settings** | Max people, Conf, Mirror, Spectrum, Auto-snap, Defaults |

### Keyboard

| Key | Action |
|-----|--------|
| `S` | Settings |
| `C` | Snap |
| `R` | Record toggle |
| `[` `]` | Confidence − / + |
| `,` `.` | Max people − / + |
| `M` | Mirror |
| `F` | Fullscreen |
| `Esc` | Close Settings, then quit |
| `Q` | Quit |

## Settings details

| Setting | Range / default |
|---------|-----------------|
| **Max people** | 1–6; MediaPipe default **1** |
| **Confidence** | 0.25–0.99; MediaPipe default **0.5** |
| **Defaults** | Resets Max=1 and Conf=0.5 ([PoseLandmarkerOptions](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarkerOptions)) |
| **Mirror** | Off by default |
| **Spectrum** | On/off; strip height always reserved (no layout jump) |
| **Auto-snap on detect** | Off by default |

## Captures

```text
viewer/captures/
  sls_YYYYMMDD_HHMMSS.jpg    # snapshots
  sls_YYYYMMDD_HHMMSS.avi    # recordings (MJPG)
  session_*.jsonl            # detect/record event log
```

Directory is gitignored.

## IR sensor gain (fixed)

| Item | Detail |
|------|--------|
| **Value** | **50** (full freenect range 1–50) |
| **What it is** | IR **camera sensor gain** only |
| **What it is not** | IR **projector** power |
| **UI** | Not shown (status stays clean) |
| **Processing** | IR PiP look only — pose uses colorized depth |

## Spectrum strip

- Under video, above main bar  
- Prefers capture device named like Kinect / USB Audio / Microsoft  
- Falls back to system default mic  
- Requires `libportaudio2` for Python `sounddevice`  

## Stack

- **PySide6** — fullscreen always-on-top window  
- **libfreenect** — depth, IR, motor, LED (ctypes)  
- **OpenCV** — colorize, draw, JPEG/AVI  
- **MediaPipe** Pose Landmarker  
- **sounddevice** — spectrum mic  
- **Flask** — only if `--ui web`  

## Files

```text
viewer/
  run.sh
  README.md
  requirements.txt
  models/                 # pose model (downloaded by run.sh)
  captures/               # local media (gitignored)
  sls_viewer/
    main.py               # entry
    qt_app.py             # UI + Settings
    pipeline.py           # capture → pose → composite
    freenect_io.py
    colorize.py
    pose.py
    skeleton.py
    spectrum.py
    session_io.py
    config.py
  web/                    # optional browser UI
```

## CLI

```bash
./run.sh --demo            # synthetic UI (no Kinect)
./run.sh --mirror          # mirror on
./run.sh --no-auto-level   # leave tilt as-is
./run.sh --led-off         # no green LED
./run.sh --ui web          # browser UI on :8765
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Window not on top | Press **F** |
| gspca / open failed | `sudo modprobe -r gspca_kinect` + `../scripts/fix-kinect-access.sh` |
| Spectrum off / no mic | `libportaudio2`; for Kinect mic: `kinect-audio-setup` + replug |
| Black window | Wait for first frame; `./run.sh --demo` |
| No DISPLAY | Need a desktop session |

Firmware / tablet image packaging: [PRODUCT-VISION.md](../../../docs/PRODUCT-VISION.md).
