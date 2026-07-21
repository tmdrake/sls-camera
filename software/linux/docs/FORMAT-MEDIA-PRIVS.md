# Format removable media — privileges

The field app **Format removable media…** rewrites a USB/SD partition as FAT32.
That is a **block-device** operation; Linux will not allow a normal user to do it
with zero privilege. Options below avoid a clumsy “full root shell” where possible.

## What the app tries (order)

1. **UDisks2** `Block.Format` via `gdbus` / `busctl`  
   - Polkit decides if the **active seat user** may format.  
   - On many desktops, removable media is allowed after a one-time auth (or always).  
2. **`mkfs.vfat`** via `pkexec` → `sudo -n` → root  
   - Requires `dosfstools`.  

Success message includes `via udisks2` or `via mkfs`.

## Workarounds (no admin on tablet)

| Approach | When to use |
|----------|-------------|
| **Host prep** | `sls-camera-firmware/scripts/prep-sls-media-usb.sh` on a PC; stick already has `SLS-MEDIA` + `sls-captures/` |
| **Already good FS** | If the card is already FAT/exFAT and writable, **skip Format** — Captures **Auto** creates `sls-captures/` on write |
| **Appliance polkit** | Ship a rule so user `sls` can format **removable** only (see below) |

## Suggested polkit rule (firmware)

Install as e.g. `/etc/polkit-1/rules.d/60-sls-udisks-format.rules` (polkit JS; adjust for distro):

```javascript
// Allow appliance user to format removable media without password (UDisks2).
// Still blocked for fixed disks by UDisks "removable" / device checks in the app.
polkit.addRule(function(action, subject) {
    if (subject.user !== "sls")
        return polkit.Result.NOT_HANDLED;
    if (action.id.indexOf("org.freedesktop.udisks2.") !== 0)
        return polkit.Result.NOT_HANDLED;
    // modify-device / filesystem-mount / etc. — keep scope tight in production
    if (action.id == "org.freedesktop.udisks2.modify-device" ||
        action.id == "org.freedesktop.udisks2.filesystem-mount" ||
        action.id == "org.freedesktop.udisks2.filesystem-mount-other-seat" ||
        action.id == "org.freedesktop.udisks2.filesystem-unmount-others") {
        return polkit.Result.YES;
    }
    return polkit.Result.NOT_HANDLED;
});
```

Test on appliance after install:

```bash
# as user sls, with a stick at /dev/sdb1 unmounted:
gdbus call --system --dest org.freedesktop.UDisks2 \
  --object-path /org/freedesktop/UDisks2/block_devices/sdb1 \
  --method org.freedesktop.UDisks2.Block.Format \
  vfat "{'label': <'SLS-MEDIA'>, 'update-partition-type': <true>}"
```

Then use the app Format button (two Yes confirms).

## Related

- App: `sls_viewer/media_format.py`, Settings **Format removable media…**  
- Firmware host wipe: `scripts/prep-sls-media-usb.sh`  
- Issue [#8](https://github.com/tmdrake/sls-camera/issues/8)  
