# Machine status snapshot

Last updated: **2026-07-16** (field app + Kinect USB Audio verified).

## Host

| Field | Value |
|-------|--------|
| Hostname | `tmdrake-optiplex7050` |
| OS | Ubuntu 26.04 LTS |
| User | `tmdrake` |
| App | `software/linux/viewer` Qt SLS |

## Kinect USB (confirmed)

```text
045e:02b0  Xbox NUI Motor
045e:02ad  Xbox NUI Audio  → after kinect-audio-setup: ALSA "Kinect USB Audio"
045e:02ae  Xbox NUI Camera
```

## Software state

| Item | State |
|------|--------|
| freenect / depth+IR | Working |
| Qt SLS app | Working (depth, IR PiP, pose, spectrum, snap/record) |
| MediaPipe defaults | Conf 0.5, max poses 1 (**Defaults** button) |
| IR sensor gain | Fixed 50 (not in UI) |
| Kinect ALSA mic | Confirmed (`arecord -l` card “Kinect USB Audio”) |
| Tablet image | Not started |

## Notes

- Prefer blacklisting / unloading `gspca_kinect` for freenect depth.  
- MSI hash mismatch on `kinect-audio-setup` documented in `docs/UBUNTU-SETUP.md`.  
