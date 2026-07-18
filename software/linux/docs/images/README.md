# Screenshots (Linux field UI)

Captured from the Phase 1 appliance VM used to prove packaging (Lubuntu **26.04** + `sls-camera-firmware` `install-appliance.sh`). Same assets live in the sibling firmware repo under `docs/images/`.

| File | Description |
|------|-------------|
| [01-guest-desktop.png](01-guest-desktop.png) | Clean Lubuntu desktop (LXQt) before launching the app |
| [02-sls-demo-app.png](02-sls-demo-app.png) | Fullscreen SLS Camera in **`--demo`** (no Kinect) |
| [03-sls-demo-hud.png](03-sls-demo-hud.png) | Demo UI with HUD (`Detected:0`, date/time, FPS) |

## How these were taken

```bash
# host: console dump of the KVM guest
virsh -c qemu:///system screenshot sls-appliance-phase1 docs/images/out.png

# guest: run UI on the logged-in X session
DISPLAY=:0 /usr/local/bin/sls-camera --demo
# or from a git checkout:
# DISPLAY=:0 ./software/linux/viewer/run.sh --demo
```

See also: [FIELD-INSTALL.md](../FIELD-INSTALL.md), firmware [FIRST-BOOT.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/FIRST-BOOT.md).
