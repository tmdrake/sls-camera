# Date & time — privileges (firmware note)

**Audience:** `sls-camera-firmware` appliance / blow-and-go images.  
**App UI:** Settings → **Date & time…** (local date, 24h time, common timezones).  
**Code:** `software/linux/viewer/sls_viewer/host_time.py` · Issue [#11](https://github.com/tmdrake/sls-camera/issues/11).

## Summary for firmware

| Question | Answer |
|----------|--------|
| Does set time need privilege? | **Yes** — `timedatectl` / `org.freedesktop.timedate1` |
| Best kiosk UX | Ship **polkit rule** below for user **`sls`** |
| Fallback | passwordless **`sudoers.d/sls-timedate`** for `/usr/bin/timedatectl` |
| No privilege on tablet | Status message explains failure; use SSH/root once |

## What the app tries (order)

1. **`timedatectl --no-ask-password set-time|set-timezone|set-ntp`**  
   - Polkit decides; with the rule below → **no password** for `sls`  
2. **`pkexec timedatectl …`** (password GUI if present)  
3. **`sudo -n timedatectl …`**  

Manual set turns **NTP off** first so offline field time is not overwritten.

## Overlay: polkit rule (ship this)

**Install path on tablet:**

```text
/etc/polkit-1/rules.d/60-sls-timedate.rules
```

**Suggested firmware tree path:**

```text
sls-camera-firmware/overlay/etc/polkit-1/rules.d/60-sls-timedate.rules
```

**File contents:**

```javascript
// SLS appliance — passwordless set time/timezone/NTP for kiosk user "sls".
// App host_time.py uses timedatectl (org.freedesktop.timedate1).
// Adjust subject.user if SLS_USER is not "sls".
polkit.addRule(function(action, subject) {
    if (subject.user !== "sls")
        return polkit.Result.NOT_HANDLED;
    if (action.id == "org.freedesktop.timedate1.set-time" ||
        action.id == "org.freedesktop.timedate1.set-timezone" ||
        action.id == "org.freedesktop.timedate1.set-ntp") {
        return polkit.Result.YES;
    }
    return polkit.Result.NOT_HANDLED;
});
```

After install:

```bash
sudo systemctl restart polkit || true
```

## Overlay: sudoers fallback (optional)

```text
/etc/sudoers.d/sls-timedate
```

```text
# Passwordless timedatectl for appliance user (Date & time Settings).
sls ALL=(root) NOPASSWD: /usr/bin/timedatectl
```

Mode **0440**; `visudo -cf` after install. Rewrite user if `SLS_USER` ≠ `sls`.

## Verify as user `sls`

```bash
timedatectl --no-ask-password set-ntp false
timedatectl --no-ask-password set-time "2026-07-22 12:00:00"
timedatectl --no-ask-password set-timezone America/Los_Angeles
timedatectl status
```

Expect exit 0 with no password prompt. Then open Settings → **Date & time…** and Apply.

## Related

| Doc | Topic |
|-----|--------|
| [FOR-FIRMWARE-TEAM.md](FOR-FIRMWARE-TEAM.md) | Blow-and-go index |
| [FORMAT-MEDIA-PRIVS.md](FORMAT-MEDIA-PRIVS.md) | Same polkit pattern for UDisks2 |
| viewer README | Settings table |
