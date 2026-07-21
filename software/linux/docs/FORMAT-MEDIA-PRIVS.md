# Format removable media — privileges (firmware note)

**Audience:** `sls-camera-firmware` appliance / blow-and-go images.  
**App UI:** Settings → **Format removable media…** (two Yes/Cancel confirms; FAT32 label **`SLS-MEDIA`** + **`sls-captures/`**).  
**Code:** `software/linux/viewer/sls_viewer/media_format.py` · Issue [#8](https://github.com/tmdrake/sls-camera/issues/8).

## Summary for firmware

| Question | Answer |
|----------|--------|
| Does format need privilege? | **Yes** — block-device write; no pure userspace wipe |
| Best kiosk UX | Ship **polkit rule** below for user **`sls`** + UDisks2 |
| Fallback | `pkexec` / passwordless `sudo` + `dosfstools` |
| No privilege on tablet | Pre-format sticks with `prep-sls-media-usb.sh` on a bench PC |

## What the app tries (order)

1. **UDisks2** `org.freedesktop.UDisks2.Block.Format` (`gdbus` / `busctl`)  
   - Polkit decides; with the rule below → **no password** for `sls`  
2. **`mkfs.vfat -F 32 -n SLS-MEDIA`** via `pkexec` → `sudo -n` → root  

Status text: `via udisks2` or `via mkfs`.

## Required packages on appliance image

| Package | Why |
|---------|-----|
| `udisks2` | Preferred format path (usually pulled by desktop) |
| `dosfstools` | `mkfs.vfat` fallback — add to apt **seeds** if missing |
| `policykit-1` / polkit | Rules engine |

## Overlay: polkit rule (ship this)

**Install path on tablet:**

```text
/etc/polkit-1/rules.d/60-sls-udisks-format.rules
```

**Suggested firmware tree path:**

```text
sls-camera-firmware/overlay/etc/polkit-1/rules.d/60-sls-udisks-format.rules
```

Wire into `install-appliance.sh` the same way as other `overlay/etc` files.

**File contents:**

```javascript
// SLS appliance — passwordless UDisks2 for kiosk user "sls" (format/mount removable).
// App media_format.py still refuses nvme / system paths / >128GiB.
// Adjust subject.user if SLS_USER is not "sls".
polkit.addRule(function(action, subject) {
    if (subject.user !== "sls")
        return polkit.Result.NOT_HANDLED;
    if (action.id.indexOf("org.freedesktop.udisks2.") !== 0)
        return polkit.Result.NOT_HANDLED;
    if (action.id == "org.freedesktop.udisks2.modify-device" ||
        action.id == "org.freedesktop.udisks2.filesystem-mount" ||
        action.id == "org.freedesktop.udisks2.filesystem-mount-other-seat" ||
        action.id == "org.freedesktop.udisks2.filesystem-unmount-others") {
        return polkit.Result.YES;
    }
    return polkit.Result.NOT_HANDLED;
});
```

After install, reload polkit if needed:

```bash
sudo systemctl restart polkit || true
```

### Verify as user `sls`

```bash
# Stick unmounted, e.g. /dev/sdb1 — DESTRUCTIVE
gdbus call --system --dest org.freedesktop.UDisks2 \
  --object-path /org/freedesktop/UDisks2/block_devices/sdb1 \
  --method org.freedesktop.UDisks2.Block.Format \
  vfat "{'label': <'SLS-MEDIA'>, 'update-partition-type': <true>}"
```

Then: SLS app → Settings → **Format removable media…** → two confirms → expect success **without** root password.

## Workarounds without polkit

| Approach | How |
|----------|-----|
| **Bench prep** | On PC: `sls-camera-firmware/scripts/prep-sls-media-usb.sh /dev/sdX` → FAT32 `SLS-MEDIA` + `sls-captures/` |
| **Skip format** | If media already FAT/exFAT and writable, Captures **Auto** creates `sls-captures/` on first snap/record |
| **Password once** | Desktop polkit may prompt; ok for lab, not kiosk |

## Blow-and-go cross-links

| Resource | Location |
|----------|----------|
| Field USB / Stage A | [ISO-AND-FIELD-USB.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/ISO-AND-FIELD-USB.md) |
| Offline mirror | [OFFLINE-MIRROR.md](https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/OFFLINE-MIRROR.md) |
| FW team one-pager | [FOR-FIRMWARE-TEAM.md](FOR-FIRMWARE-TEAM.md) |
| App captures docs | [viewer README § Captures / Format](../viewer/README.md#format-removable-media-settings) |

## Related contracts

- Quit power-off: exit **10** + firmware launcher (not this polkit rule)  
- Capture path: `SLS_CAPTURES_DIR=/data/sls-captures` when present  
