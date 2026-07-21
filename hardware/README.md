# Hardware

Shared notes for the physical SLS / Xbox 360 Kinect setup.

## Tablet fleet / hardware matrix

- **Matrix (resolutions, Settings, wipe status):** [../software/linux/docs/HARDWARE-MATRIX.md](../software/linux/docs/HARDWARE-MATRIX.md)  
- **Fleet template:** [TABLET-FLEET.md](TABLET-FLEET.md)  
- **Issue:** [#7](https://github.com/tmdrake/sls-camera/issues/7)  
- Firmware device dossiers: `sls-camera-firmware/docs/devices/` (tablet-01 RCA, tablet-02 TMAX, Kinect portable power)

## Expected contents

- Power and USB wiring notes  
- Photos of the modified or portable rig  
- Schematics for any custom add-ons  
- Tilt / mount / case notes  

## Confirmed baseline (Linux bring-up host)

- **Sensor:** Xbox 360 Kinect (NUI Motor / Audio / Camera)  
- **Power:** external Kinect PSU required  
- **IDs:** `045e:02b0`, `045e:02ad`, `045e:02ae`  
- **Linux M0:** freenect live video verified 2026-07-16 on `tmdrake-optiplex7050` — details in `software/linux/notes/BRINGUP-FREENECT.md`

Software paths:

- Windows: `software/source/`  
- Linux: `software/linux/`  

## Appliance / firmware notes

- **Captures on locked images:** after a firmware-style tablet image, the root filesystem may be **read-only**. Plan a **writable permanent volume** for investigation media (snaps, AVI, session logs) — e.g. `/data/sls-captures`, SD card, or a data partition — and point the app there via config/env. Do not rely solely on `software/linux/viewer/captures` inside a locked image.  
- **Removable / SD in the field (app v1):** Settings **Captures to = Auto** (default). New media goes to mounted **SD first**, then USB pen drive (`<mount>/sls-captures/`). Falls back to local if nothing is mounted. Optional **Copy local→media** (no silent dump on insert). Tablets are expected to be **SD-primary**; USB is fine for desk testing.  
  Details: [viewer/README.md](../software/linux/viewer/README.md#captures) · [docs/TODO.md](../docs/TODO.md) · issue [#5](https://github.com/tmdrake/sls-camera/issues/5) (closed, v1).
