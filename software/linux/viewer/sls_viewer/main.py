"""SLS viewer entry — Flask app + MJPEG stream + fullscreen web UI."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from .config import WEB_ROOT, Settings, settings
from .pipeline import FramePipeline

app = Flask(__name__, static_folder=None)
pipeline = FramePipeline(settings)


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
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
                )
            time.sleep(0.03)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="SLS Linux viewer (depth + IR + skeleton)")
    p.add_argument("--host", default=settings.host)
    p.add_argument("--port", type=int, default=settings.port)
    p.add_argument(
        "--mirror",
        action="store_true",
        help="Enable selfie-style horizontal mirror (default: off, operator behind camera)",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="Allow synthetic frames if Kinect cannot open",
    )
    p.add_argument("--device", type=int, default=0)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    settings.host = args.host
    settings.port = args.port
    settings.mirror = bool(args.mirror)
    settings.device_index = args.device
    settings.allow_demo_without_kinect = bool(args.demo)

    if not WEB_ROOT.is_dir():
        print(f"Web UI missing: {WEB_ROOT}", file=sys.stderr)
        return 1

    pipeline.start()
    print(
        f"SLS viewer → http://{settings.host}:{settings.port}/  "
        f"(fullscreen in browser; Ctrl+C stop)"
    )
    print(f"mirror={settings.mirror} demo={settings.allow_demo_without_kinect}")
    try:
        # threaded=True so MJPEG + API don't block each other
        app.run(
            host=settings.host,
            port=settings.port,
            threaded=True,
            use_reloader=False,
        )
    finally:
        pipeline.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
