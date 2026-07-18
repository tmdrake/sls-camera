# Project TODO / backlog

Living list of follow-ups for the SLS field app and appliance path.

**Dev posture:** keep iterating features on a git checkout. Packaging today =
user-local **install / uninstall** scripts (document what a field unit needs).
**Tablets** are the eventual deploy target; firmware image, sensors, and power
policy come later.

## Recording / capture

- [x] **Mux audio into recordings** — Record writes MJPG video + parallel mic WAV, then muxes into a single AVI (PCM audio) via system `ffmpeg` or `imageio-ffmpeg`. Prefers Kinect USB Audio; shares spectrum stream to avoid exclusive-open conflicts. Fallback: video AVI + sidecar WAV if mux fails.
  - Related: `software/linux/viewer/sls_viewer/session_io.py`, `spectrum.py`, `audio_device.py`
  - Closed: [GitHub #1](https://github.com/tmdrake/sls-camera/issues/1)
- [x] **Captures → removable media / SD (auto-detect)** — Settings **Captures to: Local | Auto** (default **Auto**); auto prefers **SD** then USB; writes `sls-captures/` on media; **Copy local→media** for one-shot dump; status `CAP:…`; fall back to local.
  - Issue: [#5](https://github.com/tmdrake/sls-camera/issues/5) — closed (v1); revisit priority/UX if field testing says otherwise
  - Code: `remedia.py`, `session_io`, Settings
  - Related: permanent captures on locked firmware image (below)
- [ ] **File management UI** — later Settings/menu to browse, delete, or move captures (local ↔ media) without shell access; optional free-space warning. Not required for v1 Auto path.

## Field / packaging (dev → tablet)

**Open GitHub issues (this repo):**

| Issue | Topic |
|-------|--------|
| [#2](https://github.com/tmdrake/sls-camera/issues/2) | Offline recursive apt deps + cache-based install |
| [#3](https://github.com/tmdrake/sls-camera/issues/3) | apt/Python OR-alternatives, downgrades, version conflicts |
| [#4](https://github.com/tmdrake/sls-camera/issues/4) | Optional system shutdown (or exit intent) on Quit |
| [#5](https://github.com/tmdrake/sls-camera/issues/5) | Captures → removable media / SD — **closed (v1)**; Auto default, SD then USB |

Firmware may implement offline mirrors; **product install-path and app-behavior decisions stay tracked here**.

- [x] **Install / uninstall scripts (dev packaging)** — user launcher + optional login autostart; documents host needs without a firmware image.
  - `software/linux/scripts/install-field-app.sh`
  - `software/linux/scripts/uninstall-field-app.sh`
  - Docs: `software/linux/docs/FIELD-INSTALL.md`
- [ ] **Clean the desktop before a firmware package install** — strip / replace stock Lubuntu (or similar) session chrome so a tablet does not ship a cluttered desktop; only then layer a firmware/image package.
- [ ] **Tablet firmware / image package** — sibling **`sls-camera-firmware`**. Offline debs/wheels + appliance install + future ISO. Deps/conflicts → issues #2 / #3.
- [ ] **gspca/udev one-shot** — fold or harden `fix-kinect-access.sh` into install path for true zero-touch bring-up.
- [ ] **Hardware BOM photos / wiring** in `hardware/` (Kinect + tablet + external power).
- [ ] **Permanent captures on appliance image** — firmware/locked rootfs may be read-only; store snaps/recordings on writable permanent media (`/data`, SD, data partition, USB), not only `viewer/captures` inside the image. Path via env/config for packaging.
  - Related: **Captures → removable media / SD** (runtime detect + prefer external volume)
- [x] **Battery % + charge indicator** — status bar `BAT n%` / `⚡` when sysfs battery exists; hidden on desktop
- [x] **Quit confirmation** — dialog before exit (stops REC cleanly)
- [ ] **Quit → optional power off** — app-level intent / Settings (Exit vs Shutdown); firmware launcher may already power off — product UX in app → issue #4
- [x] **Display brightness** (Settings) — sysfs backlight / brightnessctl / xrandr software fallback
- [ ] **Power management** — stable SLS on **external power** with tablet: suspend/sleep policy, USB power, avoid brownouts when Kinect + display are both on.
- [ ] **Sensor inputs** — Arduino/MCU bridge into the app (see product features).

## Product features (later)

- [x] DrakeVox word panel (5–15 min timer, TTS, auto-snap option; key `O`)
- [ ] DrakeVox external triggers beyond auto-snap (audio spike / MCU)
- [ ] Arduino / MCU sensor bridge
- [ ] Optional RGB view or color swap (Windows parity)

## Done (recent)

- [x] Live depth + IR PiP + skeletons (MediaPipe on colorized depth)
- [x] Qt Settings; Snap/Record on main bar; REC elapsed time
- [x] Spectrum strip (Kinect USB Audio after kinect-audio-setup)
- [x] MediaPipe Defaults button (conf 0.5, max poses 1) with confirm
- [x] Clear captures (confirm); blocked while recording
- [x] AVI recordings with muxed mic audio (Kinect preferred)
- [x] Kinect LED: red while REC; red flash on snap then green
- [x] Kinect video reconnect + SLS splash; stale-frame USB death detect
- [x] Spectrum / mic auto-retry when device drops
- [x] DrakeVox (~2k word list, 5–15 min, TTS, AVI burn-in)
- [x] DrakeVox on auto-snap setting (default ON; not manual Snap)
- [x] Battery status + Quit confirm + display brightness
- [x] Dev install/uninstall scripts + FIELD-INSTALL.md
