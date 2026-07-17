# Project TODO / backlog

Living list of follow-ups for the SLS field app and appliance path.

## Recording / capture

- [x] **Mux audio into recordings** — Record writes MJPG video + parallel mic WAV, then muxes into a single AVI (PCM audio) via system `ffmpeg` or `imageio-ffmpeg`. Prefers Kinect USB Audio; shares spectrum stream to avoid exclusive-open conflicts. Fallback: video AVI + sidecar WAV if mux fails.
  - Related: `software/linux/viewer/sls_viewer/session_io.py`, `spectrum.py`, `audio_device.py`

## Field / appliance

- [ ] Tablet image / autostart (Lubuntu-class)
- [ ] gspca/udev install packaging for one-shot bring-up
- [ ] Hardware BOM photos / wiring in `hardware/`

## Product features (later)

- [x] Ovilus word panel (15–30 min timer; Settings + key `O`; session log)
- [ ] Ovilus external triggers (detect / audio / MCU)
- [ ] Arduino / MCU sensor bridge
- [ ] Optional RGB view or color swap (Windows parity)

## Done (recent)

- [x] Live depth + IR PiP + skeletons (MediaPipe on colorized depth)
- [x] Qt Settings; Snap/Record on main bar; REC elapsed time
- [x] Spectrum strip (Kinect USB Audio after kinect-audio-setup)
- [x] MediaPipe Defaults button (conf 0.5, max poses 1)
- [x] AVI recordings with muxed mic audio (Kinect preferred)
- [x] Kinect video reconnect screen + infinite retry
- [x] Spectrum / mic auto-retry when device drops
- [x] Ovilus word panel (Windows word list + 15–30 min timer)
