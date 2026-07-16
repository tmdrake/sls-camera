# Machine status snapshot

Last updated: **2026-07-16** (after successful freenect video / M0).

## Host

| Field | Value |
|-------|--------|
| Hostname | `tmdrake-optiplex7050` |
| OS | Ubuntu 26.04 LTS (resolute) |
| Kernel | 7.0.0-27-generic (at snapshot) |
| User | `tmdrake` |
| Display | Desktop session with `DISPLAY=:0` (freenect GL viewer) |

## Kinect USB (confirmed)

```text
045e:02b0  Microsoft Corp. Xbox NUI Motor
045e:02ad  Microsoft Corp. Xbox NUI Audio
045e:02ae  Microsoft Corp. Xbox NUI Camera
```

This is **Kinect for Xbox 360** (original), not Kinect v2 / Xbox One.

## Software state (M0 complete)

| Item | State |
|------|--------|
| `freenect` / `libfreenect-bin` | Installed `1:0.5.3-3.3` |
| `freenect-glview` | Works — live video confirmed |
| Blacklist | `/etc/modprobe.d/blacklist-gspca-kinect.conf` → `blacklist gspca_kinect` |
| Udev | Package rules `60-libfreenect0.5t64.rules` |
| USB node perms (working) | `crw-rw-rw- root plugdev` on motor/audio/camera |
| Groups | `plugdev` active; add `video` if using V4L tools |
| Custom SLS viewer | Not built yet (`software/linux/viewer/` scaffold only) |

## Driver notes

- Prefer freenect for depth / SLS work; keep `gspca_kinect` blacklisted.
- If `gspca_kinect` reappears in `lsmod` after reboot, re-check blacklist and unload: `sudo modprobe -r gspca_kinect`.
- RGB-only V4L (`/dev/video0`) is the alternate path when gspca is loaded; not required for freenect.

## Goal for this host

Primary Linux development / field machine for freenect + SLS-style viewer under `software/linux/`.

Windows SLS Explorer remains the reference UI/behavior under `software/source/`.

Full bring-up story (errors, fixes, checklist): [BRINGUP-FREENECT.md](BRINGUP-FREENECT.md).
