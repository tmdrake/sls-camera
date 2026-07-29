# Lite mode recommendations (Atom / 2 GiB field tablets)

**Audience:** app + firmware. Target hardware is Cherry Trail (Atom x5-Z83xx),
~2 GiB RAM, **no useful GPU acceleration** for MediaPipe / OpenCV.

**Today:** `SLS_FIELD_LITE=1` / `--field-lite` already sets 7.5 FPS live+record,
pose every 2 frames, `max_poses=1`, fast Qt scale, and pauses pose during
Settings + DrakeVox speak. See [viewer README § Field Atom](../viewer/README.md)
and issue [#14](https://github.com/tmdrake/sls-camera/issues/14).

**Why Windows still feels smoother:** Kinect SDK 1.x skeleton stream is NUI
(native), not host ML. Depth colorization uses static LUTs
(`DepthColorizer.cs`). Linux approximates sticks with **MediaPipe on CPU
(XNNPACK)** on colorized depth — that tax dominates on these tablets.

This note is the prioritized backlog to harden Lite as the **real production
path** on the fleet, not a temporary band-aid.

---

## Current Lite baseline (already shipped)

| Knob | Field-lite value |
|------|------------------|
| `target_fps` / `record_fps` | 7.5 |
| `pose_every_n_frames` | 2 |
| `max_poses` | 1 |
| `display_fast` | True |
| Pose paused | Settings open + DrakeVox speak |
| FPS log | Off by default |

---

## Recommended next steps (priority order)

### 1. Depth colorize → fixed / slow adaptive LUT (high leverage, low risk)

Current path: per-frame percentile + `cv2.applyColorMap` (`colorize.py`).

- Switch Lite to a **fixed intensity → color LUT** (same idea as Windows
  `DepthColorizer` intensity table).
- Or update adaptive range only every 1–2 s, not every frame.
- Keep TURBO (or phosphor) look by baking it into the table once.

**Files:** `sls_viewer/colorize.py`, wire via `Settings.field_lite` or
`colorize_mode="lut"`.

### 2. Half-res MediaPipe input + `pose_every_n=3`

- Downscale colorized depth before `PoseEstimator.estimate()` (e.g. 0.5 →
  320×240, or 256×192 on the worst units).
- Raise default Lite `pose_every_n` from **2 → 3** (try 4 if thermal/FPS still
  bad). Hold sticks between estimates (already partially done).
- Keep `max_poses=1` hard; never rebuild landmarker for multi-person in Lite.

**Files:** `pose.py`, `pipeline.py`, `config.apply_field_lite()`.

### 3. Spectrum style whitelist for Lite

Force light styles only: **Phosphor / Classic / simple Wave**.

Disable by default in Lite: Waterfall, Glow, history/blur-heavy styles
(extra work for a ~56 px strip).

**Files:** `spectrum.py`, Settings cycle when `field_lite`.

### 4. IR PiP throttle + skip empty skeleton draws

- Update IR PiP every 2–3 frames (or disable in ultra-lite).
- Skip `draw_skeletons` when `_last_poses` is empty.
- Avoid extra BGR copies between pipeline and Qt `QImage`.

**Files:** `pipeline.py`, `qt_app.py` display path.

### 5. Recording stays AVI MJPG

- Keep **AVI MJPG @ live FPS** as field default.
- Do not push software x264 on Atom.
- On-stop MP4 only if VAAPI is probed and works; else stay AVI
  ([#20](https://github.com/tmdrake/sls-camera/issues/20)).

### 6. Optional ultra-lite fallback

When effective FPS stays below ~5 after the above:

- Hide sticks (or very coarse depth-blob sticks) instead of stuttering the UI.
- Document the visual gap vs Windows SDK sticks for operators.

Keep the existing **LITE** badge on live UI only (not burned into Record/Snap —
[#21](https://github.com/tmdrake/sls-camera/issues/21)).

---

## Proposed Lite preset (extend `apply_field_lite`)

```text
target_fps          = 7.5   (or 6.0 on thermal pain)
record_fps          = same as target
pose_every_n        = 3
max_poses           = 1
display_fast        = True
pose_input_scale    = 0.5     # new
colorize_mode       = "lut"   # new
ir_pip_every_n      = 2       # new
spectrum_style      = force light styles only
fps_log_interval_s  = 0
```

Keep env overrides so firmware can tune per tablet without a code change:

- `SLS_FIELD_LITE=1`
- `SLS_TARGET_FPS` / `SLS_RECORD_FPS`
- `SLS_POSE_EVERY_N`
- `SLS_DISPLAY_FAST`

---

## Architecture note (later, not required for next Lite pass)

| Approach | Gain on Atom | Effort |
|----------|--------------|--------|
| LUT + half-res pose + stronger throttle | High | Low — do first |
| C/C++ capture+colorize worker, Python UI | Higher | Medium |
| Full native Qt + libfreenect | Highest | High |

Stay on Python/Qt for feature velocity (DrakeVox, spectrum, captures,
reconnect) until real-tablet telemetry still fails after steps 1–4.

---

## Related

- Issue [#14](https://github.com/tmdrake/sls-camera/issues/14) — Field Atom caps
- [HARDWARE-MATRIX.md](HARDWARE-MATRIX.md) — tablet-01 / tablet-02 / KVM 2 GiB
- [LINUX-SLS-PLAN.md](LINUX-SLS-PLAN.md) — pose options vs Windows SDK
- [ARCHITECTURE.md](ARCHITECTURE.md)
- Windows reference: `software/source/KinectWpfViewers/DepthColorizer.cs`
- Root [docs/TODO.md](../../../docs/TODO.md)

*Drafted 2026-07-29 from limited-hardware redesign review.*
