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
| **Record** | AVI + mic + TTS at **20 FPS** (matches live `target_fps`); LED solid **red** while REC |
| **Reconnect** | Splash **Starting / Reconnecting to SLS Camera**; infinite retry |
| **Battery** | Status `BAT n%` / `⚡` when a battery exists (hidden on desktop) |
| **Brightness** | Settings ±10% (sysfs / brightnessctl / xrandr) |
| **Quit** | Confirms before exit; on appliance firmware powers off (exit 10) |
| **DrakeVox** | 5–15 min timer + TTS; ~2k-word list; under IR PiP; key **O** |
| **Settings** | Two-pane panel; pose, DrakeVox, captures, Format removable media, … |
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
| **Snap** | Save composite JPEG (no forced DrakeVox word); LED red→green |
| **Record** | Start/stop AVI; LED red while active |
| **Settings** | See Settings details below |

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

Settings is a **wide two-pane** dialog sized for fleet **16:10 landscape** (1280×800 / 1920×1200):

| Pane | Content |
|------|---------|
| **Left** | Controls (pose, spectrum, DrakeVox, captures, actions) — scrolls if needed |
| **Right** | Status / log (display geometry, mic, DrakeVox history, keys) |

**Close** is in the header. At startup the app logs geometry (also shown on the right pane):

```text
display: 1280x800 avail=1280x768 ar=16:10 dpr=1.0 dpi=96
display: 1920x1200 avail=1920x1168 ar=16:10 dpr=1.0 dpi=96   # tablet-02 class / VM mode
```

Firmware should leave the session in **16:10 landscape** before launch. Issue: [#6](https://github.com/tmdrake/sls-camera/issues/6) (closed). Related: [#7](https://github.com/tmdrake/sls-camera/issues/7) hardware tree.

**VM QA note (2026-07-21):** two-pane layout looks good at **1280×800** and **1920×1200**. Left pane still has **minor scrolling** at both sizes — consider scaling left-pane control buttons **slightly smaller** so the common field controls fit without scroll (or with less scroll). Track under [#7](https://github.com/tmdrake/sls-camera/issues/7).

| Setting | Range / default |
|---------|-----------------|
| **Max people** | 1–6; MediaPipe default **1** |
| **Confidence** | 0.25–0.99; MediaPipe default **0.5** |
| **Defaults** | Confirm → Max=1, Conf=0.5, **Captures to Auto** |
| **Clear captures** | Confirm, then delete files under `captures/` (blocked while REC) |
| **Mirror** | Off by default |
| **Spectrum** | On/off; strip height always reserved (no layout jump) |
| **Spectrum style** | Cycle look (saved): **Phosphor** (default), Classic, Mirror, Heat tips, Freq bands, Scope grid, Wave, Glow, Dots, Waterfall. **Defaults** restores Phosphor |
| **Auto-snap on detect** | Off by default (pose appear → Snap) |
| **DrakeVox** | **ON** = panel + timer/TTS/O; **OFF** = hide panel + stop generation |
| **DrakeVox on auto-snap** | Default **ON**; only when auto-snap fires (not manual Snap) |
| **Brightness** | ±10%; n/a if no backlight/xrandr |
| **Captures to** | **Auto** (default) or **Local** — see [Captures](#captures) |
| **Copy local→media** | Only visible when USB/SD is mounted; confirm then copy |
| **Format removable media…** | Confirm twice → erase + FAT32 the mounted SD/USB → `SLS-MEDIA` + `sls-captures/` (needs admin) — [#8](https://github.com/tmdrake/sls-camera/issues/8) |

## Captures

Field rule of thumb: **tablets will usually use an SD card**; pen drives are fine for desk testing. Default **Auto** is built for that.

### Easy mental model

| Situation | What happens |
|-----------|----------------|
| **No stick/card** | New snaps/records → **local** `viewer/captures/` |
| **Captures = Auto** (default) + media mounted | New files → **`<mount>/sls-captures/`** |
| **Both SD and USB mounted** | **SD wins** (priority); then USB; then other removable |
| **Captures = Local** | Always local, even if media is plugged in |
| **Shot local, then plug media** | Settings → **Copy local→media** (keeps local files; skips same-name same-size) |
| **Defaults** button | Also sets **Captures to Auto** (and Max=1, Conf=0.5) |

We do **not** auto-copy old local files when you plug media (avoids surprise full disks / duplicates). One explicit button is easier in the field.

### Format removable media (Settings)

One button, shown **only when a USB stick or SD card is mounted**:

**Format removable media…** → two Yes/Cancel confirms → erase that SD/USB partition → FAT32 label **`SLS-MEDIA`** → create **`sls-captures/`** → Captures **Auto**.

1. Plug SD or USB; wait until the app sees it.  
2. Settings → **Format removable media…**  
3. **Confirm 1** — shows label / device / size (default **Cancel**).  
4. **Confirm 2** — “Erase and format” (default **Cancel**; no typing).  
5. Format runs as **FAT32**. Privilege order:
   1. **UDisks2** (polkit) — often works for *removable* media as the logged-in user (may still ask once, or never if FW ships a polkit rule)
   2. **`mkfs.vfat` via pkexec / sudo** — classic root path (`dosfstools`)

**There is no pure userspace format** of a block device without some elevated right (kernel policy). Workarounds if the tablet has no admin:

| Workaround | Notes |
|------------|--------|
| Pre-format on a PC | Firmware `prep-sls-media-usb.sh` → plug into tablet; Auto captures work |
| Stick already FAT + writable | App can already write `sls-captures/` without format |
| Appliance polkit rule | Allow `sls` to `org.freedesktop.udisks2.modify-device` for removable only (FW) |

Refuses internal/nvme disks and media larger than 128 GiB.

### Auto priority (when several volumes are mounted)

| Order | Kind | How detected (typical) |
|------:|------|-------------------------|
| 1 | **SD** | `mmcblk*` (tablet internal/external SD) |
| 2 | **USB** | removable/hotplug `sd*` (pen drive) |
| 3 | Other removable | other RM/HOTPLUG mounts |

Within the same kind: more free space, then label name. Status bar shows which was chosen (`CAP:SD:…` vs `CAP:USB:…`).

### Paths

```text
# local (always available)
viewer/captures/
  sls_YYYYMMDD_HHMMSS.jpg
  sls_YYYYMMDD_HHMMSS.avi
  session_*.jsonl

# on USB pen drive or tablet SD (Auto + media mounted)
<mount>/sls-captures/
  …same filenames…
```

**Detection:** `lsblk` (USB RM/HOTPLUG + SD `mmcblk*`) and desktop automounts under `/media/$USER` and `/run/media/$USER`.  
**Status:** `CAP:SD:Label · xG free` / `CAP:USB:…` / `CAP:local` / `CAP:local (no media)`.

**Copy local→media** is hidden until media is mounted (nothing to copy to).

Local `viewer/captures/` is gitignored. Revisit priority/UX later if field use says USB-first is better; file management UI is a later TODO.

### Quick pen-drive test (dev PC)

1. `./run.sh` (Captures default **Auto**, or hit **Defaults**)  
2. Plug pen drive; wait for OS mount  
3. Status should show `CAP:USB:…`  
4. **Snap** → check stick `sls-captures/sls_….jpg`  
5. Optional: shoot local with **Captures=Local**, plug media, **Copy local→media**

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
- **Style** (Settings **Spectrum style**, saved): **Phosphor** (default), Classic, Mirror, Heat tips, Freq bands, Scope grid, Wave, Glow, Dots, Waterfall. **Defaults** restores Phosphor.  
  Glow / Waterfall do a bit more work (blur / history); the strip is only ~56px tall so cost stays modest on field tablets.

## DrakeVox

Spirit-box style word generator (not “Ovilus”). Default bank is the Digital Dowsing published list.

| Item | Detail |
|------|--------|
| **Words** | `data/drakevox_words_digitaldowsing.txt` (~2035); fallback 20 classic words if missing |
| **Timer** | Random **300–900 s** (5–15 min) between words |
| **UI** | Panel **under the IR PiP** (green text); last **5** as `HH:MM:SS WORD` |
| **TTS** | `libespeak-ng` / espeak / spd-say fallback |
| **Manual** | **DrakeVox now** or key **`O`** |
| **Auto-snap** | If **DrakeVox on auto-snap** + **Auto-snap on detect**: generate word + TTS and burn into JPEG |
| **Manual Snap** | Does **not** force a new word (may still show current panel on JPEG) |
| **Recording** | Overlay burned into AVI; TTS mixed into audio with mic |

## Kinect LED cues

| State | LED (freenect) |
|-------|----------------|
| Idle | **Green** (or off with `--led-off`) |
| Recording | Solid **red** |
| After Snap / auto-snap | Brief **red**, then restore (green, or red if still REC) |

No true orange on the Kinect; yellow is available in freenect but snap uses red→restore for a clear cue.

## Kinect reconnect

If freenect loses the camera (unplug, BUSY, power brick), the main view shows **Reconnecting to SLS Camera** and retries forever until the device returns (LED green + auto-level on success).

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

## Display wake lock (always on while running)

While the field UI is up, the app **always** holds a wake lock (no Settings toggle) so the panel does not blank mid-investigation:

| Layer | Method |
|-------|--------|
| Screensaver | D-Bus `org.freedesktop.ScreenSaver.Inhibit` |
| Idle sleep | `systemd-inhibit --what=idle:sleep` |
| X11 DPMS | `xset s off` / `xset -dpms` (re-asserted about every minute) |

Released on Quit. Status/log may show `wake-lock: …`.  
**Not tablet power-off** — firmware owns power-off on Quit. Issue [#9](https://github.com/tmdrake/sls-camera/issues/9).

## Quit (and who powers off the tablet)

**Quit** / **Q** / **Esc** (when Settings is closed) confirms, stops capture cleanly, then exits.

| Environment | Who decides power-off | App dialog | Exit code |
|-------------|----------------------|------------|-----------|
| **Dev desktop** | App default: exit only | “Quit SLS Camera?” | `0` |
| **Appliance / tablet** | **Firmware launcher** sets `SLS_QUIT_ACTION=shutdown` | “Power off this tablet?” | **`10`** |

There is **no Settings toggle** for power-off. Firmware (`sls-camera-firmware` → `/usr/local/bin/sls-camera`) owns host shutdown:

- `SLS_ON_QUIT=app` — honor exit codes  
- `SLS_QUIT_ACTION=shutdown` — app uses power-off dialog + exit **10**  
- `SLS_QUIT_FALLBACK=none` — exit **0** does **not** power off (app must send **10**)  
- Launcher runs `poweroff` when it sees exit **10** (sudoers)

Dev machines never set that env, so Quit returns to the desktop.  
The app **never** runs `poweroff` itself — only exit code **10** for the launcher. Issue [#4](https://github.com/tmdrake/sls-camera/issues/4).

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
    freenect_io.py        # depth/IR + LED + reconnect
    colorize.py
    pose.py
    skeleton.py
    spectrum.py           # FFT + mic retry + PCM sinks
    session_io.py         # Snap / Record + A/V mux + clear captures
    drakevox.py           # 5–15 min timer, word bank, overlay
    tts.py                # espeak TTS for DrakeVox + AVI mix
    battery.py
    backlight.py
    audio_device.py       # Kinect mic picker
    config.py
  data/                   # DrakeVox word list (Digital Dowsing extract)
  web/                    # optional browser UI
```

## CLI (`./run.sh`)

`run.sh` creates the venv if needed, ensures PySide6 + the pose model, then runs `python -m sls_viewer` with your args.

```bash
./run.sh --help              # argparse help only (no gspca/portaudio preflight noise)
./run.sh                     # live Kinect; reconnects forever if missing
./run.sh --demo              # fallback synthetic frames if freenect cannot open
./run.sh --mirror            # horizontal mirror
./run.sh --no-auto-level     # leave tilt as-is
./run.sh --led-off           # no green idle LED
./run.sh --ui web            # browser UI (default host/port 127.0.0.1:8765)
./run.sh --host 0.0.0.0 --port 8765 --ui web
./run.sh --device 0          # freenect device index (multi-Kinect)
```

Equivalent without the wrapper (after venv exists):

```bash
.venv/bin/python -m sls_viewer --help
```

### Flags (summary)

| Flag | Default | Meaning |
|------|---------|---------|
| `--ui {qt,web}` | `qt` | Fullscreen always-on-top Qt, or browser UI |
| `--host ADDR` | `127.0.0.1` | Web bind address |
| `--port N` | `8765` | Web port |
| `--mirror` | off | Mirror depth/IR |
| `--demo` | off | **Fallback only:** if freenect open fails, use synthetic depth/IR instead of reconnecting forever. **Does not** skip a working Kinect |
| `--no-auto-level` | auto-level on | Skip tilt to 0° on start |
| `--led-off` | green idle LED | Leave Kinect LED off |
| `--device INDEX` | `0` | Freenect device index |

Full text (examples + keyboard shortcuts) is always from argparse:

```bash
./run.sh --help
```

### `run.sh` preflight (when not showing help)

| Check | Behavior |
|-------|----------|
| gspca_kinect loaded | WARNING — freenect often fails; unload or run `fix-kinect-access.sh` |
| PortAudio | Probes `libportaudio.so.2` via Python ctypes (and multiarch paths). NOTE only if truly missing: `sudo apt install libportaudio2` |
| Startup banner | Printed for normal launches; **skipped** for `--help` / `-h` |

### `--demo` behavior (important)

| Situation | Result |
|-----------|--------|
| Kinect opens OK | **Live camera** (same as without `--demo`) |
| Kinect will not open, **no** `--demo` | Splash **Reconnecting to SLS Camera** forever |
| Kinect will not open, **with** `--demo` | Synthetic depth/IR UI (“demo mode”) |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Window not on top | Press **F** |
| gspca / open failed | `sudo modprobe -r gspca_kinect` + `../scripts/fix-kinect-access.sh` |
| Spectrum off / no mic | `sudo apt install libportaudio2`; Kinect mic: `kinect-audio-setup` + replug |
| Spectrum `mic retry…` | Unplug/replug or wait; ensure device in `arecord -l` |
| False “libportaudio not found” | Should be rare after `run.sh` ctypes check; confirm `ldconfig -p \| grep portaudio` or `ls /usr/lib/*/libportaudio.so*` |
| Record AVI has no sound | Install `ffmpeg` or `imageio-ffmpeg` (in venv); check flash for sidecar WAV |
| Soft / loud mic | App does not set gain — use `pavucontrol` or `alsamixer` on the capture source |
| Kinect RECONNECTING | Power brick + USB; freenect retries automatically |
| No Kinect / test UI only | `./run.sh --demo` (synthetic frames **if** open fails) |
| Black window | Wait for first frame; or `--demo` if no camera |
| No DISPLAY | Need a desktop session |

Firmware / tablet image packaging: [PRODUCT-VISION.md](../../../docs/PRODUCT-VISION.md).
