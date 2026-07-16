# Hardware

Shared notes for the physical SLS / Xbox 360 Kinect setup.

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
