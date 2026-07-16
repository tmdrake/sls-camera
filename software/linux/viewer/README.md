# SLS Linux viewer (backend + kiosk web UI)

**Product goal:** same as Windows SLS Explorer main screen — **depth-first view with skeleton stick-figure overlay** — shippable as a **tablet Linux appliance** later.

Plan: [../docs/LINUX-SLS-PLAN.md](../docs/LINUX-SLS-PLAN.md) · Vision: [../../../docs/PRODUCT-VISION.md](../../../docs/PRODUCT-VISION.md).

## UI decision

- **Field UI:** web page in **kiosk browser** (touch-friendly, Lubuntu/tablet)  
- **Processing:** Python **backend service** (freenect + pose + overlay + stream)  
- OpenCV window: optional **dev spike only**, not the product chrome  

## Status

Scaffold only. Host freenect path is proven (`freenect-glview`, M0). Next: M1 backend depth stream → M2 sticks → M3/M4 kiosk image → M5 Ovilus/sensors.

## Planned layout

```text
viewer/
  README.md
  requirements.txt
  run.sh                 # dev: backend + browser
  sls_viewer/
    __init__.py
    main.py              # service entry
    depth.py
    pose.py
    skeleton.py
    stream.py            # local HTTP / MJPEG / WebSocket
    config.py
  web/
    index.html           # SLS main view
    app.js
    style.css
```

## UX targets

- Depth-first main view + skeleton overlay  
- Un-mirrored default (operator behind camera)  
- Dark theme, large touch targets  
- Later: Ovilus panel, extra sensor tiles (Arduino bridge)  

## Dependencies (expected)

- System: `libfreenect`, Python 3, browser for kiosk  
- Python: OpenCV (compose), MediaPipe (or lighter pose), freenect bindings, small web stack  

Do not add large binary blobs or Windows SDK installers here.
