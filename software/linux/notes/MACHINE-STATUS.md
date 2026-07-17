# Machine status snapshot

Last updated: **2026-07-16** (AVI+audio mux + reconnect verified).

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
| Record | AVI MJPG + PCM mic (Kinect preferred); imageio-ffmpeg mux |
| Reconnect | Infinite freenect retry + RECONNECTING frame; mic retry ~2s |
| MediaPipe defaults | Conf 0.5, max poses 1 (**Defaults** button) |
| IR sensor gain | Fixed 50 (not in UI) |
| Mic gain | OS/Pulse default (app does not set ALSA level) |
| Kinect ALSA mic | Confirmed (`arecord -l` card “Kinect USB Audio”) |
| Dev install scripts | Present (`install-field-app.sh` / uninstall) |
| Tablet firmware image | Not started (clean desktop first) |

## Notes

- Prefer blacklisting / unloading `gspca_kinect` for freenect depth.  
- MSI hash mismatch on `kinect-audio-setup` documented in `docs/UBUNTU-SETUP.md`.  
