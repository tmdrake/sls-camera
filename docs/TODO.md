# Project TODO / backlog

Living list of follow-ups for the SLS field app and appliance path.

## Recording / capture

- [ ] **Mux audio into recordings** — today Record is video-only (OpenCV AVI/MJPG of composite frames). Spectrum uses Kinect USB Audio (or system mic) separately. Desired: save mic audio with the video (e.g. parallel WAV + ffmpeg mux to mp4/mkv, or an A/V writer). Prefer Kinect USB Audio when present.
  - Related: `software/linux/viewer/sls_viewer/session_io.py`, `spectrum.py`

## Field / appliance

- [ ] Tablet image / autostart (Lubuntu-class)
- [ ] gspca/udev install packaging for one-shot bring-up
- [ ] Hardware BOM photos / wiring in `hardware/`

## Product features (later)

- [ ] Ovilus word panel (timer / triggers)
- [ ] Arduino / MCU sensor bridge
- [ ] Optional RGB view or color swap (Windows parity)

## Done (recent)

- [x] Live depth + IR PiP + skeletons (MediaPipe on colorized depth)
- [x] Qt Settings; Snap/Record on main bar; REC elapsed time
- [x] Spectrum strip (Kinect USB Audio after kinect-audio-setup)
- [x] MediaPipe Defaults button (conf 0.5, max poses 1)
