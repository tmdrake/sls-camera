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
- [x] **Captures → removable media / SD (auto-detect)** — Settings **Captures to: Local | Auto** (default **Auto**); auto prefers **SD** then USB (tablets expected SD-primary; pen drive OK for desk tests); writes `sls-captures/` on media; **Copy local→media** only when media mounted (no silent copy on insert); status `CAP:…`; fall back to local; **Defaults** resets Captures to Auto.
  - Issue: [#5](https://github.com/tmdrake/sls-camera/issues/5) — **closed (v1)**; keep Auto/SD-first unless field use says otherwise
  - Docs: [viewer/README.md § Captures](../software/linux/viewer/README.md#captures), [hardware/README.md](../hardware/README.md)
  - Code: `remedia.py`, `session_io`, Settings
  - Related: permanent captures on locked firmware image (below)
- [ ] **File management UI** — later Settings/menu to browse, delete, or move captures (local ↔ media) without shell access; optional free-space warning. Not required for v1 Auto path.

## Field / packaging (dev → tablet)

**Open GitHub issues (this repo):**

| Issue | Topic |
|-------|--------|
| [#2](https://github.com/tmdrake/sls-camera/issues/2) | Offline apt seeds + cache install — **closed** |
| [#3](https://github.com/tmdrake/sls-camera/issues/3) | OR-alternatives / conflicts — **tracking** |
| [#4](https://github.com/tmdrake/sls-camera/issues/4) | Quit → power off — **closed** |
| [#5](https://github.com/tmdrake/sls-camera/issues/5) | Captures Auto SD/USB — **closed (v1)** |
| [#6](https://github.com/tmdrake/sls-camera/issues/6) | Geometry log + Settings scroll — **closed** |
| [#7](https://github.com/tmdrake/sls-camera/issues/7) | Hardware matrix — **docs v1** (post-wipe geometry still pending) |
| [#8](https://github.com/tmdrake/sls-camera/issues/8) | Format/prepare media from Settings — **closed** |
| [#9](https://github.com/tmdrake/sls-camera/issues/9) | Keep display awake while UI runs — **closed** |

Firmware may implement offline mirrors; **product install-path and app-behavior decisions stay tracked here**.

- [x] **Install / uninstall scripts (dev packaging)** — user launcher + optional login autostart; documents host needs without a firmware image.
  - `software/linux/scripts/install-field-app.sh`
  - `software/linux/scripts/uninstall-field-app.sh`
  - Docs: `software/linux/docs/FIELD-INSTALL.md`
- [x] **Offline-safe apt install (#2)** — seed list + `install-apt-deps.sh` (cache → `/var/cache/apt/archives` + `--no-download`; never blanket `dpkg -i`); `--with-apt-deps` / `--deb-cache` / `SLS_OFFLINE=1`; uninstall `--purge-apt-deps` (safe seeds only); honors `SLS_CAPTURES_DIR`.
  - `software/linux/packages/apt-packages.txt`, `apt-purge-safe.txt`
  - **FW one-pager:** [FOR-FIRMWARE-TEAM.md](../software/linux/docs/FOR-FIRMWARE-TEAM.md)
  - Align with firmware `vendor/debs` + [OFFLINE-MIRROR.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/OFFLINE-MIRROR.md)
  - Closed: [GitHub #2](https://github.com/tmdrake/sls-camera/issues/2); conflicts tracking: [#3](https://github.com/tmdrake/sls-camera/issues/3)
- [ ] **Clean the desktop before a firmware package install** — strip / replace stock Lubuntu (or similar) session chrome so a tablet does not ship a cluttered desktop; only then layer a firmware/image package.
- [ ] **Tablet firmware / image package** — sibling **`sls-camera-firmware`**. Offline debs/wheels + appliance install + future ISO. Deps/conflicts → issues #2 / #3.
- [ ] **gspca/udev one-shot** — fold or harden `fix-kinect-access.sh` into install path for true zero-touch bring-up.
- [ ] **Hardware BOM photos / wiring** in `hardware/` (Kinect + tablet + external power).
- [ ] **Permanent captures on appliance image** — firmware/locked rootfs may be read-only; store snaps/recordings on writable permanent media (`/data`, SD, data partition, USB), not only `viewer/captures` inside the image. Path via env/config for packaging.
  - Related: **Captures → removable media / SD** (runtime detect + prefer external volume)
- [x] **Battery % + charge indicator** — status bar `BAT n%` / `⚡` when sysfs battery exists; hidden on desktop
- [x] **Quit confirmation** — dialog before exit (stops REC cleanly)
- [x] **Quit → power off (firmware contract)** — env `SLS_QUIT_ACTION=shutdown` (appliance launcher); app dialog + exit **10**; **no** Settings toggle (firmware owns host poweroff). Dev stays exit-only.
  - Closed: [GitHub #4](https://github.com/tmdrake/sls-camera/issues/4)
  - Code: `host_power.py`, `qt_app.py`, `config.py`
- [x] **Display brightness** (Settings) — sysfs backlight / brightnessctl / xrandr software fallback
- [x] **Settings fit small tablets (#6)** — log `display: WxH avail=… dpr=… dpi=…` at Qt start; Settings in `QScrollArea` capped ~90% available height; Close pinned; action buttons 2×2
  - Closed: [GitHub #6](https://github.com/tmdrake/sls-camera/issues/6)
- [x] **Keep display awake (#9)** — always-on wake lock while UI runs (no Settings toggle); D-Bus screensaver inhibit + `systemd-inhibit idle:sleep` + `xset -dpms`; release on Quit
  - Code: `display_inhibit.py`, `qt_app.py`
  - Closed: [GitHub #9](https://github.com/tmdrake/sls-camera/issues/9)
- [x] **Hardware matrix (#7)** — [HARDWARE-MATRIX.md](../software/linux/docs/HARDWARE-MATRIX.md) + [hardware/TABLET-FLEET.md](../hardware/TABLET-FLEET.md); tablet-01/02 rows linked to FW devices; post-wipe Qt geometry still TBD per unit
  - Issue: [#7](https://github.com/tmdrake/sls-camera/issues/7)
- [x] **Format / prepare media (#8)** — Settings **Prepare media** (mkdir sls-captures/) + **Format for SLS…** (FAT32 double-confirm, pkexec/sudo); safety rails in `media_format.py`
  - Closed: [GitHub #8](https://github.com/tmdrake/sls-camera/issues/8)
- [ ] **Power management** — stable SLS on **external power** with tablet: suspend/sleep policy, USB power, avoid brownouts when Kinect + display are both on.
- [ ] **Sensor inputs** — Arduino/MCU bridge into the app (see product features).

## Product features (later)

- [x] DrakeVox word panel (5–15 min timer, TTS, auto-snap option; key `O`)
- [ ] **Branding** — configurable product/overlay names (e.g. replace `***DrakeVox***` title, app chrome) without hardcoding
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
- [x] Quit → optional power off (Settings + exit 10 + env)
- [x] DrakeVox overlay title `***DRAKEVOX***` in LED magenta
- [x] Dev install/uninstall scripts + FIELD-INSTALL.md
- [x] Offline-safe apt (#2) + FOR-FIRMWARE-TEAM.md handoff
- [x] Settings scroll + geometry log (#6)
- [x] Keep display on while field UI runs (#9)
- [x] Hardware matrix docs (#7) + format/prepare media (#8)
