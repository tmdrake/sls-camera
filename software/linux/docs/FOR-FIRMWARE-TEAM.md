# For the firmware team (read this first)

**One-pager** for `sls-camera-firmware` work. Product app lives here; offline image work is sibling.

| Repo | Role |
|------|------|
| **`sls-camera`** (this) | App source of truth · seed list · offline-**safe** install helpers · issues |
| **`sls-camera-firmware`** | `vendor/` mirror · `install-appliance.sh` · future ISO |

Full install narrative: [FIELD-INSTALL.md](FIELD-INSTALL.md).  
Offline mirror details: [firmware OFFLINE-MIRROR.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/OFFLINE-MIRROR.md).

---

## Golden rules (do not break)

| ✅ Do | ❌ Don’t |
|-------|----------|
| Fetch **recursive** hard deps (`FETCH_DEPS=1`) | Ship **seed-only** offline packs |
| Install **seeds** via apt from cache | `dpkg -i vendor/debs/*.deb` (OR conflicts) |
| Copy debs → `/var/cache/apt/archives` then `apt-get install --no-install-recommends --no-download <seeds>` | Assume network on tablet |
| Drop `libav*-extra*`, `libjack0` from fetch packs | Use offline-only `file://` apt that forces python downgrades |
| `pip install --no-index --find-links=vendor/wheels` when wheels exist | `pip install --upgrade pip` from PyPI offline |
| Track new package fights on **[sls-camera#3](https://github.com/tmdrake/sls-camera/issues/3)** | Only note conflicts in firmware chat |

**Why:** Phase 1 Lubuntu 26.04 — seed-only packs left half-configured packages; blanket `dpkg -i` hit both sides of OR alternatives (`libjack0` vs `libjack-jackd2-0`, `libavcodec` vs `*-extra`).

---

## App-side tools (closed [sls-camera#2](https://github.com/tmdrake/sls-camera/issues/2))

| Path | What |
|------|------|
| [`packages/apt-packages.txt`](../packages/apt-packages.txt) | **Seed** list (keep in sync with firmware `packages/apt-packages.txt`; app also wants `espeak-ng`) |
| [`packages/apt-purge-safe.txt`](../packages/apt-purge-safe.txt) | Safe uninstall purge only (never python3 / GUI base) |
| [`scripts/install-apt-deps.sh`](../scripts/install-apt-deps.sh) | Online **or** cache install (same rules as appliance) |
| [`scripts/install-field-app.sh`](../scripts/install-field-app.sh) | Dev launcher + `--with-apt-deps` / `--deb-cache` |
| [`scripts/uninstall-field-app.sh`](../scripts/uninstall-field-app.sh) | Remove launcher; optional `--purge-apt-deps` |

### Commands that must work tomorrow

```bash
# Layout: ~/sls-camera + ~/sls-camera-firmware (siblings)

# 1) On a build host with network — refresh recursive offline pack
cd ~/sls-camera-firmware
./scripts/10-fetch-offline.sh          # FETCH_DEPS=1 default → ~360 debs

# 2) Prove app installer against that cache (no surprise dpkg -i)
cd ~/sls-camera
./software/linux/scripts/install-apt-deps.sh --print-seeds
./software/linux/scripts/install-apt-deps.sh \
  --deb-cache ~/sls-camera-firmware/vendor/debs
# or:
./software/linux/scripts/install-field-app.sh --with-apt-deps \
  --deb-cache ~/sls-camera-firmware/vendor/debs

# 3) Strict offline (fails if cache incomplete)
SLS_OFFLINE=1 ./software/linux/scripts/install-apt-deps.sh \
  --deb-cache ~/sls-camera-firmware/vendor/debs

# 4) Auto-detect: if vendor/debs exists next door, --with-apt-deps finds it
./software/linux/scripts/install-field-app.sh --with-apt-deps
```

Env: `SLS_DEB_CACHE`, `SLS_OFFLINE=1`, `SLS_APT_YES=1`.

---

## Appliance contracts the app already honors

| Contract | App behavior |
|----------|----------------|
| **`SLS_CAPTURES_DIR`** | Local snaps/records dir (firmware sets `/data/sls-captures`) |
| **`/data/sls-captures`** | Dev wrapper exports `SLS_CAPTURES_DIR` when that dir exists |
| **Quit exit codes** | `0` clean quit · **`10` power-off** · `11` relaunch (reserved) |
| **`SLS_QUIT_ACTION=shutdown`** | Appliance default in launcher — app shows “Power off?” and exits **10** |
| **`SLS_ON_QUIT=app`** + **`SLS_QUIT_FALLBACK=none`** | Launcher powers off **only** on exit 10 |
| App **wake lock** | Always on while field UI runs (not host power-off; no Settings toggle) |

**Host power-off is firmware-owned** (launcher + sudoers). App has no Power-off Settings toggle.  
Details: [viewer README § Quit](../viewer/README.md#quit) · [FIELD-INSTALL § Quit](FIELD-INSTALL.md#quit-vs-power-off-app-vs-appliance).

---

## Seed list sync

When adding a **system** package the app needs:

1. Add to **`sls-camera/software/linux/packages/apt-packages.txt`**
2. Mirror in **`sls-camera-firmware/packages/apt-packages.txt`**
3. Re-run `10-fetch-offline.sh` on the **same Ubuntu series** as the tablet (e.g. 26.04)
4. Comment on [#3](https://github.com/tmdrake/sls-camera/issues/3) if apt fights alternatives

Do **not** put Microsoft Kinect UAC audio firmware in either public repo (`kinect-audio-setup` on device only).

---

## Smoke checklist (before freezing a field pack)

- [ ] `FETCH_DEPS=1` fetch on matching Ubuntu; `vendor/debs` has hundreds of debs + `PACKAGE-LIST.txt`
- [ ] No `libav*-extra*.deb` / `libjack0_*.deb` left in the pack
- [ ] `SLS_OFFLINE=1 install-apt-deps.sh --deb-cache vendor/debs` succeeds (or appliance install)
- [ ] Wheels: `pip install --no-index --find-links=vendor/wheels -r requirements.txt`
- [ ] App: `./run.sh --demo` smoke (no Kinect required for UI)
- [ ] With Kinect: depth + spectrum after `kinect-audio-setup` (manual, not in public mirror)
- [ ] Captures: `SLS_CAPTURES_DIR=/data/sls-captures` or Auto SD/USB path
- [ ] Lubuntu 26.04 autologin uses **SDDM**, not LightDM

---

## Issues

| Issue | Status |
|-------|--------|
| [#2](https://github.com/tmdrake/sls-camera/issues/2) Offline apt cache install | **Closed** — `install-apt-deps.sh` |
| [#3](https://github.com/tmdrake/sls-camera/issues/3) OR-alternatives / new conflicts | **Open tracker** — comment new finds |
| [#4](https://github.com/tmdrake/sls-camera/issues/4) Quit → power off | **Closed** — exit 10 + Settings |
| [#5](https://github.com/tmdrake/sls-camera/issues/5) Captures → SD/USB | **Closed** (v1 Auto SD-first) |

App backlog: [docs/TODO.md](../../../docs/TODO.md).
