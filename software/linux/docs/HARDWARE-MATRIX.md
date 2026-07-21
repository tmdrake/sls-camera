# Hardware matrix (field tablets)

Product home for **screen variants + device BOM** while wipe-loading appliances.  
Issue: [#7](https://github.com/tmdrake/sls-camera/issues/7) · UI geometry/scroll: [#6](https://github.com/tmdrake/sls-camera/issues/6) (closed).

Firmware per-device notes (msinfo imports, landscape lock):  
[`sls-camera-firmware/docs/devices/`](https://github.com/tmdrake/sls-camera-firmware/tree/main/docs/devices) · [HARDWARE.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/HARDWARE.md)

## How to fill a row

After first appliance boot on a unit:

1. Open SLS Camera; copy the startup / status flash line:
   ```text
   display: 1280x800 avail=1280x768 dpr=1.0 dpi=96
   ```
2. Open **Settings** — confirm all controls reachable (two-pane + scroll).
3. Optional: `xrandr` / `xdpyinfo` in a terminal; photos of ports.
4. Update the table below + link a device note (app or firmware `docs/devices/`).

**Template (copy into a device note):** see [hardware/TABLET-FLEET.md](../../../hardware/TABLET-FLEET.md).

## Fleet matrix

| Unit ID | Make / model | Native (Windows) | Appliance target | RAM | CPU | Qt geometry @ boot | Settings UI | Kinect USB | Captures | Quit power-off | Status |
|---------|--------------|------------------|------------------|-----|-----|--------------------|-------------|------------|----------|----------------|--------|
| **tablet-01** | RCA **W101AS23T2** | 800×1280 portrait | **1280×800** landscape | 2 GB | Atom x5-Z8350 | *fill after wipe* | *pending* | kit ready | *pending* | *pending* | Wipe candidate — [FW note](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/devices/rca-w101as23t2.md) |
| **tablet-02** | TMAX **TM800W610L** | 1200×1920 portrait | **1920×1200** landscape | 2 GB | Atom x5-Z8300 | *fill after wipe* | *pending* | kit ready | *pending* | *pending* | Wipe candidate — [FW note](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/devices/tablet-02.md) |
| **kvm-phase1** | QEMU/KVM Lubuntu 26.04 | — | **1280×800** / **1920×1200** | VM | host | 1280×800 avail≈1280×768 · 1920×1200 avail≈1920×1168 · ar=16:10 dpr=1 dpi=96 | Two-pane **OK**; left pane **minor scroll** at both sizes — try slightly smaller left-pane buttons | passthrough lab | Auto/local OK | exit 10 OK | **Packaging reference** (layout QA 2026-07-21) |

### Shared field kit

- Xbox 360 Kinect + **portable power** (not bus-powered)  
- Details: [FW kinect-portable-power.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/devices/kinect-portable-power.md)

## Product display target: **16:10 landscape**

Fleet tablets (after firmware landscape lock) are designed for **16:10**:

| Ratio | Example | Fleet role |
|-------|---------|------------|
| **16:10** | **1280×800**, **1920×1200** | **Primary** — tablet-01 / tablet-02 / KVM |
| 16:9 | 1280×720, 1920×1080 | Supported (slightly shorter); Settings still scrolls |
| 3:2 | Surface-class | Usually more vertical room |
| Portrait | 800×1280 raw glass | Firmware **locks landscape** before app |

Same **aspect**, different **pixel count**: 1920×1200 is a sharper 16:10, not a different shape.  
App Settings `_fit_to_screen` prefers a wide two-pane dialog on 16:10-ish panels.

### App UI expectations by resolution

| Class | Typical | Settings / UI |
|-------|---------|----------------|
| Fleet tablet-01 | **1280×800** 16:10 | Two-pane Settings; left scroll if needed |
| Fleet tablet-02 | **1920×1200** 16:10 | More room; usually little control scroll |
| Phase 1 VM | 1280×800 16:10 | Same as tablet-01 class |
| Short / old | 1024×600 (~17:10) | Scroll required; log geometry |
| HiDPI 200% on 800p | logical ~640×400 | High risk — note dpr in matrix |

App depth canvas remains **1280×720** (16:9 composite) scaled with keep-aspect on the 16:10 panel (letterbox/pillarbox as needed).

## App features that support this matrix

| Feature | Issue | Status |
|---------|-------|--------|
| Geometry log at start | #6 | Done — `display: WxH avail=… dpr=… dpi=…` |
| Two-pane scrollable Settings | #6 | Done |
| Wake lock (always while running) | #9 | Done |
| Quit → power off (exit 10) | #4 | Done |
| Captures Auto SD-first | #5 | Done |
| Format / prepare media | #8 | App Settings (see viewer README) |

## Acceptance checklist (#7)

- [x] Template + matrix live in app docs  
- [x] Geometry log exists so units are comparable  
- [x] Settings operable on 1280×800 class (two-pane + scroll)  
- [x] Two device classes documented (tablet-01, tablet-02) with native vs locked res  
- [ ] At least one **real tablet** row filled with **post-wipe** Qt geometry + Settings pass  
- [ ] Photos in `hardware/` when available  

When a wipe completes, replace `*pending*` cells and set **Status** to e.g. `appliance OK 2026-…`.
