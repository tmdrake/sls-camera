# Host package seeds

| File | Purpose |
|------|---------|
| [`apt-packages.txt`](apt-packages.txt) | Apt **seeds** for the field app / appliance |
| [`apt-purge-safe.txt`](apt-purge-safe.txt) | Optional uninstall purge (never base system) |

Install them with:

```bash
../scripts/install-apt-deps.sh
../scripts/install-field-app.sh --with-apt-deps
```

**Firmware team:** start at [docs/FOR-FIRMWARE-TEAM.md](../docs/FOR-FIRMWARE-TEAM.md).  
Keep seeds aligned with `sls-camera-firmware/packages/apt-packages.txt`.
