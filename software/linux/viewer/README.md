# SLS Linux viewer

**Fullscreen native Qt app** (always on top) for Xbox 360 Kinect SLS-style monitoring.

## Features (current)

| Area | Behavior |
|------|----------|
| **Main view** | Full-screen **colorized depth + skeleton** |
| **PiP** | Small **IR + skeleton** (top-right) |
| **Pose** | MediaPipe on **colorized depth** only |
| **Spectrum** | FFT strip under video; prefers **Kinect USB Audio**; **retries** if mic drops |
| **Snap** | JPEG (current DrakeVox panel if visible); Kinect LED **red → green** (or red if still REC) |
| **Auto-snap** | Optional on pose appear; **DrakeVox on auto-snap** (default ON) adds word+TTS into that JPEG |
| **Record** | AVI + mic + TTS; Kinect LED solid **red** while REC; green/off when stopped |
| **Reconnect** | Splash **Starting / Reconnecting to SLS Camera**; infinite retry |
| **Battery** | Status `BAT n%` / `⚡` when a battery exists (hidden on desktop) |
| **Brightness** | Settings ±10% (sysfs / brightnessctl / xrandr) |
| **Quit** | Confirms before exit (stops recording cleanly) |
| **DrakeVox** | 5–15 min timer + TTS; ~2k-word list; under IR PiP; key **O** |
| **Settings** | Pose, mirror, spectrum, auto-snap, DrakeVox, brightness, Defaults/Clear (confirm) |
| **On open** | LED green, tilt auto-level 0°, IR sensor gain **50** (fixed) |

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
# DrakeVox TTS (CLI optional; libespeak-ng often enough for synthesis):
sudo apt install -y espeak-ng
# optional host ffmpeg (viewer also uses imageio-ffmpeg binary if needed):
sudo apt install -y ffmpeg
# Kinect mic for spectrum + Record audio (one-time; MS firmware — see docs):
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
| **Settings** | Max people, Conf, Mirror, Spectrum, Auto-snap, DrakeVox, Brightness, Defaults (confirm), Clear captures (confirm) |

### Keyboard

| Key | Action |
|-----|--------|
| `S` | Settings |
| `C` | Snap |
| `R` | Record toggle |
| `O` | DrakeVox generate now |
| `[` `]` | Confidence − / + |
| `,` `.` | Max people − / + |
| `M` | Mirror |
| `F` | Fullscreen |
| `Esc` | Close Settings, then quit |
| `Q` | Quit (with confirmation) |

## Settings details

| Setting | Range / default |
|---------|-----------------|
| **Max people** | 1–6; MediaPipe default **1** |
| **Confidence** | 0.25–0.99; MediaPipe default **0.5** |
| **Defaults** | Resets Max=1 and Conf=0.5 ([PoseLandmarkerOptions](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarkerOptions)) |
| **Mirror** | Off by default |
| **Spectrum** | On/off; strip height always reserved (no layout jump) |
| **Auto-snap on detect** | Off by default |
| **DrakeVox** | **ON** = show panel + generate (timer/TTS/O); **OFF** = hide panel + stop all generation |
| **DrakeVox on auto-snap** | Default **ON**; fires word+TTS into JPEG only on auto-snap (not manual Snap) |

## Captures

```text
viewer/captures/
  sls_YYYYMMDD_HHMMSS.jpg    # snapshots
  sls_YYYYMMDD_HHMMSS.avi    # recordings (MJPG video + PCM mic audio)
  session_*.jsonl            # detect/record event log
```

Directory is gitignored.

### Record audio

1. While recording, mic PCM is captured in parallel (16 kHz mono float → int16 WAV).
2. Prefers **Kinect USB Audio** (same picker as spectrum); shares the spectrum PortAudio stream so the device is not opened twice.
3. On stop, muxes video + WAV into **`sls_*.avi`** (video stream copy + `pcm_s16le`).
4. If mux fails (no ffmpeg / imageio-ffmpeg), keeps `*_video.avi` + `*_audio.wav` sidecar.

### Mic gain / sensitivity (defaults)

The app **does not set** ALSA or Pulse capture gain. Levels come from the OS/device:

| Layer | Default behavior |
|-------|------------------|
| **App** | No gain knob; float samples used as-is for WAV; spectrum bars auto-normalize for display only |
| **Sample rate / format** | 16 kHz, mono, float32 capture → int16 in file |
| **Pulse/PipeWire source** | Typically **100% / full** capture volume for a new USB source (Kinect after firmware) |
| **Kinect array** | Hardware beamforming is in MS UAC firmware — app uses channel 0 of the UAC device |
| **Sensitivity** | Not adjustable in-app; raise OS input volume (`pavucontrol` / `alsamixer`) if soft |

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
- **Retries** every ~2s if the mic drops (unplug / power cycle) — strip shows `mic retry…`  
- Requires `libportaudio2` for Python `sounddevice`  

## DrakeVox

Spirit-box style word generator (Linux name; not “Ovilus”). Word list matches the classic Windows explorer vocabulary.

| Item | Detail |
|------|--------|
| **Words** | Digital Dowsing list (`data/drakevox_words_digitaldowsing.txt`, ~2k words); fallback 20 classic words if file missing |
| **Timer** | Random **5–15 minutes** between words |
| **UI** | Taller panel **under the IR PiP**; **last 5** as `HH:MM:SS WORD` (newest first) |
| **TTS** | Speaks each word (`libespeak-ng` / `espeak-ng` / `espeak`; live fallback `spd-say`) |
| **History** | Last 5 on overlay; last 12 in Settings; `session_*.jsonl` event `drakevox` |
| **Manual** | Settings **DrakeVox now** or key **`O`** |
| **Recording** | Overlay **burned into AVI video**; spoken audio **mixed into AVI** with mic |

## Kinect reconnect

If freenect loses the camera (unplug, BUSY, power brick), the main view shows **RECONNECTING TO KINECT…** and retries forever until the device returns (LED green + auto-level on success).

| Timing | Value | Meaning |
|--------|-------|---------|
| **Stale frame** | **1.5 s** | No new depth/IR callback → treat as dead |
| **Frame wait** | **2.0 s** | Max wait for a fresh frame before raising |
| **Open wait** | **4.0 s** | Max wait for first frames after open (returns ASAP) |
| **Reconnect sleep** | **2.0 s** | Delay between full freenect close/reopen attempts |
| **Open retries** | **3** | Internal tries per prepare |

Startup and reconnect show a splash: **Starting SLS Camera** / **Reconnecting to SLS Camera** (not a blank screen).

Power/USB loss often prints `USB camera marked dead` / iso transfer `-4` in the console; the app should switch to the reconnect splash within ~2 s.

## Battery (tablet)

When Linux exposes a battery under `/sys/class/power_supply` (or UPower), the status bar shows e.g. `BAT 64%` or `BAT 87% ⚡` (charging). **Hidden** on desktops with no battery.

### Display brightness (Settings)

| Backend | When |
|---------|------|
| **sysfs** `/sys/class/backlight` | Laptops/tablets with a real panel backlight |
| **brightnessctl** | If installed and permitted |
| **xrandr --brightness** | Desktop/HDMI software dim (works on many monitors) |

Settings → **Brightness − / +** (±10%). Tooltip shows which backend is active. If nothing works, shows **n/a**. Value is saved in `user_settings.json` when changed.

## Quit

**Quit** / **Q** / **Esc** (when Settings is closed) asks **Quit SLS Camera?** before exiting so a recording can stop cleanly.

## Stack

- **PySide6** — fullscreen always-on-top window  
- **libfreenect** — depth, IR, motor, LED (ctypes)  
- **OpenCV** — colorize, draw, JPEG/AVI  
- **MediaPipe** Pose Landmarker  
- **sounddevice** — spectrum + record mic + TTS playback  
- **espeak-ng** (lib or CLI) — DrakeVox TTS synthesis for live + AVI  
- **imageio-ffmpeg** / host **ffmpeg** — AVI audio mux  
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
    pipeline.py           # capture → pose → composite + reconnect
    freenect_io.py
    colorize.py
    pose.py
    skeleton.py
    spectrum.py           # FFT + mic retry + PCM sinks
    session_io.py         # Snap / Record + A/V mux
    drakevox.py             # random word 5–15 min, timestamped overlay
    tts.py                  # espeak TTS for DrakeVox + AVI mix
    audio_device.py       # Kinect mic picker
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
| Spectrum `mic retry…` | Unplug/replug or wait; ensure device in `arecord -l` |
| Record AVI has no sound | Install `ffmpeg` or `imageio-ffmpeg` (in venv); check flash for sidecar WAV |
| Soft / loud mic | App does not set gain — use `pavucontrol` or `alsamixer` on the capture source |
| Kinect RECONNECTING | Check power brick + USB; freenect keeps retrying automatically |
| Black window | Wait for first frame; `./run.sh --demo` |
| No DISPLAY | Need a desktop session |

Firmware / tablet image packaging: [PRODUCT-VISION.md](../../../docs/PRODUCT-VISION.md).
