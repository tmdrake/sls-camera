# Tablet fleet (hardware tree)

Inventory view for field tablets. Full matrix + process:  
[software/linux/docs/HARDWARE-MATRIX.md](../software/linux/docs/HARDWARE-MATRIX.md) · issue [#7](https://github.com/tmdrake/sls-camera/issues/7).

Firmware device dossiers (msinfo, landscape lock):  
`sls-camera-firmware/docs/devices/`.

## Current units

| ID | Model | Target landscape | Notes |
|----|-------|------------------|--------|
| tablet-01 | RCA W101AS23T2 | 1280×800 | 2 GB, Goodix touch, Atom Z8350 |
| tablet-02 | TMAX TM800W610L | 1920×1200 | 2 GB, Atom Z8300, x64 Windows was installed |

## Per-device template

```markdown
# Device: <make model>

**Unit ID:** `tablet-NN`

| Field | Value |
|-------|--------|
| Panel native | |
| Appliance locked | |
| Qt geometry @ boot | display: WxH avail=… dpr=… dpi=… |
| Touch | |
| OS base | Lubuntu 26.04 appliance |
| App pin | |
| Firmware pin | |
| Settings UI | OK / scroll / clipped |
| Kinect USB | |
| Captures | /data/sls-captures · Auto SD |
| Quit power-off | exit 10 |
| Photos | |
| Notes | |
```

## Photos / wiring

Add under `hardware/` when available (front, back, ports, Kinect + portable PSU).
