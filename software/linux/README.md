# Linux SLS path

Ubuntu / freenect path for the same Xbox 360 Kinect (NUI) hardware used by the Windows SLS Explorer under `software/source/`.

## Status

| Milestone | Status |
|-----------|--------|
| **M0** — freenect install + live `freenect-glview` | **Done** (2026-07-16, OptiPlex + Kinect 360) |
| **M1+M2 app** — web viewer: big depth+skel, small IR+skel | **Implemented** under `viewer/` (needs Kinect free of gspca) |
| **M3** — touch web kiosk chrome polish | Partial (fullscreen + large buttons) |
| **M4** — tablet appliance image | Not started |
| **M5** — Ovilus + Arduino sensors | Not started |

- Bring-up: [notes/BRINGUP-FREENECT.md](notes/BRINGUP-FREENECT.md)  
- **Parity plan:** [docs/LINUX-SLS-PLAN.md](docs/LINUX-SLS-PLAN.md)  
- **Product vision:** [../../docs/PRODUCT-VISION.md](../../docs/PRODUCT-VISION.md)  
- **UI:** **Qt fullscreen always-on-top** (optional web) — `viewer/run.sh`  

## Goal

**Same as the Windows UI:** main screen = depth feed with **SLS skeleton stick-figure overlay** (see `software/source/example/KinectWindow.xaml` and root `AGENTS.md`).

1. Live **depth** stream — freenect path proven in M0  
2. **Stick-figure / skeleton** on that main depth view — planned via freenect + pose engine (MediaPipe primary)  
3. Later: spectrum, Ovilus, session tools (Windows extras)

## Layout

```text
software/linux/
  README.md                 # this file
  docs/
    UBUNTU-SETUP.md         # install, udev, gspca, troubleshooting
    ARCHITECTURE.md         # stack layers
    LINUX-SLS-PLAN.md       # Windows parity goal, skeleton options, milestones
  scripts/
    check-kinect.sh         # USB / driver smoke check
    install-freenect.sh     # apt install + blacklist + groups
    fix-kinect-access.sh    # fix -3 / subdevice open failures
  viewer/
    README.md               # planned Python SLS UI (scaffold)
  notes/
    MACHINE-STATUS.md       # host + sensor snapshot
    BRINGUP-FREENECT.md     # M0 success log and failure/fix notes
```

## Quick start (M0 — already verified on this host)

```bash
# from repo root
./software/linux/scripts/check-kinect.sh

# live freenect OpenGL view (depth / color)
freenect-glview
```

If open fails with `Could not open camera: -3`:

```bash
./software/linux/scripts/fix-kinect-access.sh
# new terminal, then:
freenect-glview
```

Full install steps: [docs/UBUNTU-SETUP.md](docs/UBUNTU-SETUP.md).

## Relation to Windows code

| Path | Role |
|------|------|
| `software/source/` | Windows WPF + Kinect SDK 1.x / .NET (reference SLS Explorer) |
| `software/linux/` | Ubuntu freenect + future open skeleton/UI stack |
| `hardware/` | Shared camera mod / power / wiring notes |
| `docs/` | Cross-platform project brief |

Do **not** treat this as a separate product repo unless the Linux app later ships on its own. Keep history and hardware notes here.
