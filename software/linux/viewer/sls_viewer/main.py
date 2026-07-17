"""SLS viewer entry — Qt fullscreen app (default) or optional web UI."""

from __future__ import annotations

import argparse
import sys
import time

from .config import WEB_ROOT, settings
from .pipeline import FramePipeline

# user_settings.json already applied in config.settings at import


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="SLS Linux viewer (depth + IR + skeleton, fullscreen)"
    )
    p.add_argument(
        "--ui",
        choices=("qt", "web"),
        default="qt",
        help="UI backend: qt = fullscreen always-on-top (default); web = browser kiosk",
    )
    p.add_argument("--host", default=settings.host)
    p.add_argument("--port", type=int, default=settings.port)
    p.add_argument(
        "--mirror",
        action="store_true",
        help="Enable horizontal mirror (default: off)",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="Allow synthetic frames if Kinect cannot open",
    )
    p.add_argument(
        "--no-auto-level",
        action="store_true",
        help="Do not tilt motor to 0° on start",
    )
    p.add_argument(
        "--led-off",
        action="store_true",
        help="Leave Kinect LED off (default: green while running)",
    )
    p.add_argument("--device", type=int, default=0)
    return p.parse_args(argv)


def run_web(pipeline: FramePipeline) -> int:
    from flask import Flask, Response, jsonify, request, send_from_directory

    app = Flask(__name__, static_folder=None)

    @app.get("/")
    def index():
        return send_from_directory(WEB_ROOT, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name: str):
        return send_from_directory(WEB_ROOT, name)

    @app.get("/api/status")
    def api_status():
        return jsonify(
            {
                "status": pipeline.status,
                "fps": round(pipeline.fps, 2),
                "poses": pipeline.poses_count,
                "mirror": pipeline.mirror,
            }
        )

    @app.post("/api/mirror")
    def api_mirror():
        data = request.get_json(silent=True) or {}
        if "mirror" in data:
            pipeline.mirror = bool(data["mirror"])
        else:
            pipeline.mirror = not pipeline.mirror
        return jsonify({"mirror": pipeline.mirror})

    @app.get("/stream.mjpg")
    def stream_mjpg():
        boundary = b"frame"

        def generate():
            while True:
                jpeg = pipeline.get_jpeg()
                if jpeg:
                    yield (
                        b"--" + boundary + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: "
                        + str(len(jpeg)).encode()
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                time.sleep(0.03)

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    if not WEB_ROOT.is_dir():
        print(f"Web UI missing: {WEB_ROOT}", file=sys.stderr)
        return 1

    print(
        f"SLS web UI → http://{settings.host}:{settings.port}/  "
        f"(optional; prefer --ui qt for field use)"
    )
    try:
        app.run(
            host=settings.host,
            port=settings.port,
            threaded=True,
            use_reloader=False,
        )
    finally:
        pipeline.stop()
    return 0


def main(argv=None):
    args = parse_args(argv)
    settings.host = args.host
    settings.port = args.port
    settings.mirror = bool(args.mirror)
    settings.device_index = args.device
    settings.allow_demo_without_kinect = bool(args.demo)
    settings.auto_level = not bool(args.no_auto_level)
    settings.led_green = not bool(args.led_off)

    pipeline = FramePipeline(settings)
    pipeline.start()
    print(
        f"UI={args.ui} mirror={settings.mirror} demo={settings.allow_demo_without_kinect} "
        f"led_green={settings.led_green} auto_level={settings.auto_level}"
    )

    try:
        if args.ui == "web":
            return run_web(pipeline)

        from .qt_app import run_qt

        print("SLS Qt UI — fullscreen always-on-top (Esc/Q quit, M mirror, F fullscreen)")
        code = run_qt(pipeline)
        return code
    finally:
        pipeline.stop()


if __name__ == "__main__":
    raise SystemExit(main())
