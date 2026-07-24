# For the firmware team (read this first)

**One-pager** for `sls-camera-firmware` work. Product app lives here; offline image / blow-and-go media is the sibling repo.

| Repo | Role |
|------|------|
| **`sls-camera`** (this) | App source of truth · seed list · offline-**safe** install helpers · UI contracts · issues |
| **`sls-camera-firmware`** | `vendor/` mirror · `install-appliance.sh` · field USB · future ISO |

| Doc | Topic |
|-----|--------|
| [FIELD-INSTALL.md](FIELD-INSTALL.md) | Dev host install / uninstall |
| [FORMAT-MEDIA-PRIVS.md](FORMAT-MEDIA-PRIVS.md) | **Polkit rule** for Format removable media (no root password) |
| [HARDWARE-MATRIX.md](HARDWARE-MATRIX.md) | Fleet tablets, **16:10**, geometry log |
| [firmware OFFLINE-MIRROR.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/OFFLINE-MIRROR.md) | Recursive debs / wheels / model |
| [firmware ISO-AND-FIELD-USB.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/ISO-AND-FIELD-USB.md) | **Blow-and-go** Stage A/B media |
| [firmware FIRST-BOOT.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/FIRST-BOOT.md) | After appliance install |
| [firmware POWER-AND-DISPLAY.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/POWER-AND-DISPLAY.md) | Landscape, DPMS, no-suspend |

---

## Blow-and-go install (resources)

**Goal:** tech wipes tablet → OS → one offline pack → field-ready SLS.

### Media roles (do not mix)

| Stick | Label / role | Contents | When |
|-------|----------------|----------|------|
| **OS installer** | Stock **Lubuntu 26.04** ISO (dd / Rufus / Ventoy) | Live + Calamares | Wipe eMMC, install OS |
| **SLS field USB** | FAT32 **`SLS-MEDIA`** | Offline firmware tree + `install-from-usb.sh` | After OS reboot → appliance |

Docs & scripts live in **`sls-camera-firmware`**:

| Resource | Path / link |
|----------|-------------|
| Blow-and-go plan | [`docs/ISO-AND-FIELD-USB.md`](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/ISO-AND-FIELD-USB.md) |
| Build field USB | `scripts/50-build-field-usb.sh` |
| Prep empty FAT stick | `scripts/prep-sls-media-usb.sh` (also used for capture media) |
| Stamp installer stick notes | `scripts/stamp-installer-usb.sh` + `media/installer-usb/` |
| Appliance install (on target) | `scripts/install-appliance.sh` or **`install-from-usb.sh`** on the field stick |
| Offline fetch | `scripts/10-fetch-offline.sh` (`FETCH_DEPS=1`) |
| Live session / landscape | [`docs/LIVE-SESSION.md`](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/LIVE-SESSION.md) |
| VM rebuild lab | [`docs/VM-REBUILD.md`](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/VM-REBUILD.md) |
| First boot | [`docs/FIRST-BOOT.md`](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/FIRST-BOOT.md) |
| Power / display policy | [`docs/POWER-AND-DISPLAY.md`](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/POWER-AND-DISPLAY.md) |

### Typical sequence (Stage A)

```text
1. Build offline pack on a networked host
     cd ~/sls-camera-firmware && ./scripts/10-fetch-offline.sh
     ./scripts/20-sync-app.sh   # pin current sls-camera main
2. Write SLS-MEDIA stick
     ./scripts/prep-sls-media-usb.sh /dev/sdX   # or 50-build-field-usb.sh
3. On tablet: install Lubuntu 26.04 from OS ISO → reboot to eMMC
4. Plug SLS-MEDIA → run install-from-usb.sh (or copy tree + install-appliance.sh)
5. First boot: SDDM autologin sls → landscape lock → SLS app
6. Smoke: --demo or Kinect; copy geometry log into HARDWARE-MATRIX
```

App-side offline apt check (optional on build host):

```bash
cd ~/sls-camera
SLS_OFFLINE=1 ./software/linux/scripts/install-apt-deps.sh \
  --deb-cache ~/sls-camera-firmware/vendor/debs
```

---

## Golden rules (offline apt — do not break)

| ✅ Do | ❌ Don’t |
|-------|----------|
| Fetch **recursive** hard deps (`FETCH_DEPS=1`) | Ship **seed-only** offline packs |
| Install **seeds** via apt from cache | `dpkg -i vendor/debs/*.deb` (OR conflicts) |
| Copy debs → `/var/cache/apt/archives` then `apt-get install --no-install-recommends --no-download <seeds>` | Assume network on tablet |
| Drop `libav*-extra*`, `libjack0` from fetch packs | Use offline-only `file://` apt that forces python downgrades |
| `pip install --no-index --find-links=vendor/wheels` when wheels exist | `pip install --upgrade pip` from PyPI offline |
| Track new package fights on **[sls-camera#3](https://github.com/tmdrake/sls-camera/issues/3)** | Only note conflicts in firmware chat |

App tools: [`packages/apt-packages.txt`](../packages/apt-packages.txt), [`scripts/install-apt-deps.sh`](../scripts/install-apt-deps.sh) (closed [#2](https://github.com/tmdrake/sls-camera/issues/2)).  
Keep seeds aligned with firmware `packages/apt-packages.txt` (app also wants **`espeak-ng`**).

---

## Format removable media — polkit (please ship on appliance)

### Why

App Settings **Format removable media…** (two Yes confirms, FAT32 `SLS-MEDIA` + `sls-captures/`) needs to write a block device. It tries:

1. **UDisks2** `Block.Format` (polkit)  
2. **`mkfs.vfat`** via `pkexec` / `sudo -n`

Without polkit/sudo, operators hit a **root password** prompt — bad for kiosk.  
**There is no fully unprivileged format**; the right fix is a **narrow polkit rule** for user `sls`.

### What to install (firmware overlay)

**Path:** `/etc/polkit-1/rules.d/60-sls-udisks-format.rules`  
(Copy from app doc sample; full notes: [FORMAT-MEDIA-PRIVS.md](FORMAT-MEDIA-PRIVS.md).)

```javascript
// SLS appliance: allow kiosk user to format/mount removable media via UDisks2
// without password. App still refuses nvme/system disks in media_format.py.
polkit.addRule(function(action, subject) {
    if (subject.user !== "sls")
        return polkit.Result.NOT_HANDLED;
    if (action.id.indexOf("org.freedesktop.udisks2.") !== 0)
        return polkit.Result.NOT_HANDLED;
    if (action.id == "org.freedesktop.udisks2.modify-device" ||
        action.id == "org.freedesktop.udisks2.filesystem-mount" ||
        action.id == "org.freedesktop.udisks2.filesystem-mount-other-seat" ||
        action.id == "org.freedesktop.udisks2.filesystem-unmount-others") {
        return polkit.Result.YES;
    }
    return polkit.Result.NOT_HANDLED;
});
```

Also ensure package **`dosfstools`** is in the offline seed list (for mkfs fallback) and **udisks2** is present (usually with desktop).

### Bench alternative (no polkit on tablet)

```bash
# On a PC (sudo) — same as capture-media prep
./scripts/prep-sls-media-usb.sh /dev/sdX
# Label SLS-MEDIA + sls-captures/; plug into tablet → Captures Auto
```

### Verify after appliance install

```bash
# as user sls, stick unmounted e.g. /dev/sdb1:
gdbus call --system --dest org.freedesktop.UDisks2 \
  --object-path /org/freedesktop/UDisks2/block_devices/sdb1 \
  --method org.freedesktop.UDisks2.Block.Format \
  vfat "{'label': <'SLS-MEDIA'>, 'update-partition-type': <true>}"
```

Then app: Settings → **Format removable media…** → should complete **without** root password when the rule is active. Status flash may say `via udisks2`.

**App code:** `software/linux/viewer/sls_viewer/media_format.py`  
**Issue:** [#8](https://github.com/tmdrake/sls-camera/issues/8) (closed; polkit is firmware deploy)

---

## Display target (fleet)

| Target | Detail |
|--------|--------|
| **Aspect** | **16:10 landscape** after `sls-lock-landscape` |
| **Examples** | tablet-01 **1280×800** · tablet-02 **1920×1200** · KVM **1280×800** |
| **App Settings** | Sized for 16:10 two-pane dialog; scrolls if short |
| **Geometry log** | Startup: `display: … ar=16:10 dpr=…` — paste into [HARDWARE-MATRIX.md](HARDWARE-MATRIX.md) |

Portrait native glass must be rotated **before** the app (firmware).

---

## Kinect tilt — use `--no-auto-level` on field units (#10)

Field kits use a **fixed mount** (no operator tilt). The app **default** still auto-levels the motor to **0°** on open/reconnect (lab/tripod convenience).

**Do not change the app default for this.** Appliance launcher should pass the existing CLI flag:

```bash
# In overlay /usr/local/bin/sls-camera (or desktop Exec):
./run.sh --no-auto-level "$@"
# or ensure the flag is always present for field:
./run.sh --no-auto-level
```

| Flag | Effect |
|------|--------|
| **`--no-auto-level`** | **No tilt command** on start/reconnect (recommended field) |
| *(default, no flag)* | Auto-level tilt to 0° (lab / adjustable mounts) |
| **`--led-off`** | Optional — turns off idle green LED; **keep LED on** for REC/snap cues |

**Keep the Kinect LED** (green idle / red REC / snap flash). LED is separate from tilt; only skip auto-level.

App still **enumerates** the motor USB ID via freenect — that is fine. Flag only stops **commanding** the motor.

Viewer CLI table: [viewer/README.md](../viewer/README.md) · issue [#10](https://github.com/tmdrake/sls-camera/issues/10).

## Appliance contracts the app already honors

| Contract | App behavior |
|----------|----------------|
| **`SLS_CAPTURES_DIR`** | Local snaps/records dir (firmware sets `/data/sls-captures`) |
| **`/data/sls-captures`** | Dev wrapper exports when dir exists |
| **Quit exit codes** | `0` clean quit · **`10` power-off** · `11` relaunch (reserved) |
| **`SLS_QUIT_ACTION=shutdown`** | Launcher default — app “Power off?” + exit **10** |
| **`SLS_ON_QUIT=app`** + **`SLS_QUIT_FALLBACK=none`** | Power off **only** on exit 10 |
| **Wake lock** | Always on while field UI runs (not host power-off) |
| **Format media** | UDisks2 then mkfs; two Yes confirms; FAT32 `SLS-MEDIA` |
| **Date & time** | Settings → **Date & time…**; needs polkit/sudoers ([DATE-TIME-PRIVS.md](DATE-TIME-PRIVS.md)) |
| **Field tilt** | Launcher passes **`--no-auto-level`** (see above) |
| **Hide cursor** | Optional **`--hide-cursor`** or **`SLS_HIDE_CURSOR=1`** (touch kiosk) |
| **Field lite (Atom)** | **`SLS_FIELD_LITE=1`** or **`--field-lite`** — 7.5 FPS live+record, pose every 2, fast scale ([#14](https://github.com/tmdrake/sls-camera/issues/14)) |
| **Perf knobs** | `SLS_TARGET_FPS` · `SLS_RECORD_FPS` · `SLS_POSE_EVERY_N` · `SLS_SHOW_FPS` · `SLS_DISPLAY_FAST` |
| **App pin (2026-07-24)** | Prefer `main` ≥ **WAV→PipeWire TTS** (field-lite DrakeVox play; PortAudio flaky on RCA) — [SESSION-2026-07-24.md](SESSION-2026-07-24.md) · [viewer README](../viewer/README.md#drakevox-tts-playback-field--rca-vs-vm) |

**Host power-off is firmware-owned** (launcher + `sudoers.d/sls-poweroff`).  
App does **not** call `poweroff` itself — only exit code 10.

---

## Seed list sync

1. Edit **`sls-camera/software/linux/packages/apt-packages.txt`**  
2. Mirror **`sls-camera-firmware/packages/apt-packages.txt`**  
3. Re-run `10-fetch-offline.sh` on matching Ubuntu series  
4. Comment on [#3](https://github.com/tmdrake/sls-camera/issues/3) if apt fights  

Do **not** put Microsoft Kinect UAC audio firmware in public trees (`kinect-audio-setup` on device only).

---

## Smoke checklist (before freezing a field pack)

- [ ] `FETCH_DEPS=1` fetch; hundreds of debs + `PACKAGE-LIST.txt`  
- [ ] No `libav*-extra*.deb` / `libjack0_*.deb` in pack  
- [ ] Offline seed install works (`SLS_OFFLINE=1` or appliance script)  
- [ ] Wheels + pose model offline  
- [ ] App smoke `--demo`; Kinect + spectrum when audio firmware present  
- [ ] DrakeVox TTS: **tablet-class VM** for latency smoke; **real RCA** for panel audio (mixer + WAV path) — [#13](https://github.com/tmdrake/sls-camera/issues/13)  
- [ ] RCA: `sls-audio-speakers` (OUTVOL); DrakeVox now **audible** (not word-only)  
- [ ] Field tablets: launcher **`SLS_FIELD_LITE=1`** or `--field-lite` (FPS log **off** by default; optional `SLS_SHOW_FPS=1`) — [#14](https://github.com/tmdrake/sls-camera/issues/14)  
- [ ] Crash relaunch: `SLS_QUIT_ON_ERROR=restart` (freenect unplug 139)  
- [ ] Captures: `/data/sls-captures` and/or Auto SD/USB  
- [ ] Quit → exit 10 → poweroff (appliance)  
- [ ] **Polkit format rule** installed; Format media works without root password  
- [ ] **Polkit timedate rule** (+ optional sudoers); Settings → Date & time works without password  
- [ ] Launcher passes **`--no-auto-level`** (no tilt motor on open)  
- [ ] Landscape **16:10**; geometry log → hardware matrix  
- [ ] SDDM autologin (not LightDM) on Lubuntu 26.04  

---

## Issues

| Issue | Status |
|-------|--------|
| [#2](https://github.com/tmdrake/sls-camera/issues/2) Offline apt | **Closed** |
| [#3](https://github.com/tmdrake/sls-camera/issues/3) OR-conflicts | **Open tracker** |
| [#4](https://github.com/tmdrake/sls-camera/issues/4) Quit power-off | **Closed** (exit 10) |
| [#5](https://github.com/tmdrake/sls-camera/issues/5) Captures Auto | **Closed** |
| [#6](https://github.com/tmdrake/sls-camera/issues/6) Settings geometry | **Closed** |
| [#7](https://github.com/tmdrake/sls-camera/issues/7) Hardware matrix | **Open** — fill post-wipe row on real tablet |
| [#8](https://github.com/tmdrake/sls-camera/issues/8) Format media | **Closed** — ship polkit for kiosk UX |
| [#9](https://github.com/tmdrake/sls-camera/issues/9) Wake lock | **Closed** |
| [#10](https://github.com/tmdrake/sls-camera/issues/10) Kinect tilt | **Closed** — `--no-auto-level` + no motor command |
| [#11](https://github.com/tmdrake/sls-camera/issues/11) Date & time | **Closed** — Settings UI + [DATE-TIME-PRIVS.md](DATE-TIME-PRIVS.md) polkit/sudoers |
| [#12](https://github.com/tmdrake/sls-camera/issues/12) Battery gauge | **Closed** — icon + fill on status bar |
| [#13](https://github.com/tmdrake/sls-camera/issues/13) DrakeVox TTS | **Closed** — async/once mixer/pose-pause; use with `SLS_FIELD_LITE=1` on Atom |
| [#14](https://github.com/tmdrake/sls-camera/issues/14) Field Atom FPS | **Caps shipped**; FPS log **opt-in only**; residual = optional GPU blit |
| [#15](https://github.com/tmdrake/sls-camera/issues/15) Win98 spectrum | **Closed** — time-domain PCM wave style |

Day logs: [SESSION-2026-07-22.md](SESSION-2026-07-22.md) · [SESSION-2026-07-24.md](SESSION-2026-07-24.md) · App backlog: [docs/TODO.md](../../../docs/TODO.md).
