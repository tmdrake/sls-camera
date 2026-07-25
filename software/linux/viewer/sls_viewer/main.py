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
        prog="sls_viewer",
        description=(
            "SLS Linux field viewer — Xbox 360 Kinect depth + IR PiP + "
            "skeleton sticks (MediaPipe), fullscreen Qt by default."
        ),
        epilog=(
            "Examples:\n"
            "  ./run.sh\n"
            "  ./run.sh --mirror\n"
            "  ./run.sh --demo\n"
            "  ./run.sh --ui web --host 0.0.0.0 --port 8765\n"
            "  ./run.sh --led-off --no-auto-level --device 0\n"
            "  ./run.sh --field-lite          # Atom: 7.5 FPS, pose every 2, TTS pose-pause\n"
            "  SLS_FIELD_LITE=1 ./run.sh      # same via env (firmware launcher)\n"
            "\n"
            "Keyboard (Qt): S settings · C snap · R record · O DrakeVox · "
            "[ and ] confidence · , and . max people · "
            "Q quit · Esc close settings then quit · F fullscreen · M mirror"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--ui",
        choices=("qt", "web"),
        default="qt",
        help="UI backend: qt = fullscreen always-on-top (default); "
        "web = browser UI on --host/--port",
    )
    p.add_argument(
        "--host",
        default=settings.host,
        metavar="ADDR",
        help=f"Web UI bind address (default: {settings.host})",
    )
    p.add_argument(
        "--port",
        type=int,
        default=settings.port,
        metavar="N",
        help=f"Web UI port (default: {settings.port})",
    )
    p.add_argument(
        "--mirror",
        action="store_true",
        help="Mirror depth/IR horizontally (default: off)",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help=(
            "Test without a Kinect: synthetic depth/IR only "
            "(does not open freenect / USB camera)"
        ),
    )
    p.add_argument(
        "--no-auto-level",
        action="store_true",
        help="Do not auto-level tilt motor to 0° on start (default: auto-level on)",
    )
    p.add_argument(
        "--led-off",
        action="store_true",
        help="Leave Kinect LED off (default: green while idle)",
    )
    p.add_argument(
        "--device",
        type=int,
        default=0,
        metavar="INDEX",
        help="Freenect device index when multiple Kinects are present (default: 0)",
    )
    p.add_argument(
        "--hide-cursor",
        action="store_true",
        help=(
            "Hide the mouse pointer (field / touch kiosk). "
            "Also enabled by SLS_HIDE_CURSOR=1. Default: show cursor."
        ),
    )
    p.add_argument(
        "--field-lite",
        action="store_true",
        help=(
            "Atom / 2GB preset (#14): target+record 7.5 FPS, pose every 2 frames, "
            "fast display scale, and TTS pose-pause during speak. "
            "Also SLS_FIELD_LITE=1. (Default mode keeps sticks live while talking.)"
        ),
    )
    p.add_argument(
        "--target-fps",
        type=float,
        default=None,
        metavar="N",
        help="Cap live pipeline FPS (default 20; field-lite 7.5). Env: SLS_TARGET_FPS",
    )
    p.add_argument(
        "--record-fps",
        type=float,
        default=None,
        metavar="N",
        help="AVI writer FPS (default 20; field-lite 7.5). Env: SLS_RECORD_FPS",
    )
    p.add_argument(
        "--pose-every-n",
        type=int,
        default=None,
        metavar="N",
        help="Run MediaPipe every N frames (default 1; field-lite 2). Env: SLS_POSE_EVERY_N",
    )
    p.add_argument(
        "--show-fps",
        action="store_true",
        help="Show effective FPS in status bar. Env: SLS_SHOW_FPS=1",
    )
    p.add_argument(
        "--display-fast",
        action="store_true",
        help=(
            "Use FastTransformation for main view scale (less CPU than smooth). "
            "Implied by --field-lite. Env: SLS_DISPLAY_FAST=1"
        ),
    )
    p.add_argument(
        "--freenect-inproc",
        action="store_true",
        help=(
            "Load libfreenect in-process (legacy). Default isolates freenect in a "
            "subprocess so USB unplug GPF does not kill the UI (#16). "
            "Env: SLS_FREENECT_ISOLATE=0"
        ),
    )
    p.add_argument(
        "--mp4",
        action="store_true",
        help=(
            "Opt-in: finalize Record as H.264 MP4 (share-friendly) instead of "
            "default MJPG AVI (#20). Capture still uses MJPG temp; encode on Stop. "
            "Env: SLS_RECORD_MP4=1. Falls back to AVI if encode fails."
        ),
    )
    p.add_argument(
        "--hardware-encode",
        action="store_true",
        help=(
            "Prefer VAAPI H.264 when using --mp4 / SLS_RECORD_MP4 (Intel/Atom). "
            "Env: SLS_HARDWARE_ENCODE=1. Soft-fallback libx264 then AVI."
        ),
    )
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


def _env_hide_cursor() -> bool:
    import os

    raw = (os.environ.get("SLS_HIDE_CURSOR") or "").strip().lower()
    return raw in ("1", "true", "yes", "on", "hide")


def main(argv=None):
    args = parse_args(argv)
    settings.host = args.host
    settings.port = args.port
    settings.mirror = bool(args.mirror)
    settings.device_index = args.device
    settings.allow_demo_without_kinect = bool(args.demo)
    settings.auto_level = not bool(args.no_auto_level)
    settings.led_green = not bool(args.led_off)
    settings.hide_cursor = bool(args.hide_cursor) or _env_hide_cursor()

    # Performance load caps (#14) — CLI then env (env can refine individual knobs)
    if bool(args.field_lite):
        settings.apply_field_lite()
    if args.target_fps is not None and args.target_fps > 0:
        settings.target_fps = max(1.0, min(60.0, float(args.target_fps)))
    if args.record_fps is not None and args.record_fps > 0:
        settings.record_fps = max(1.0, min(60.0, float(args.record_fps)))
    if args.pose_every_n is not None and args.pose_every_n >= 1:
        settings.pose_every_n_frames = min(30, int(args.pose_every_n))
    if bool(args.show_fps):
        settings.show_fps = True
    if bool(args.display_fast):
        settings.display_fast = True
    if bool(getattr(args, "mp4", False)):
        settings.record_format = "mp4"
    if bool(getattr(args, "hardware_encode", False)):
        settings.hardware_encode = True
    settings.apply_perf_from_env()
    # Freenect isolate default ON; --freenect-inproc or SLS_FREENECT_ISOLATE=0 disables
    if bool(getattr(args, "freenect_inproc", False)):
        import os as _os

        _os.environ["SLS_FREENECT_ISOLATE"] = "0"

    # Probe H.264 path once at startup (VAAPI / libx264 / none) — not deferred to first REC
    try:
        from .session_io import probe_h264_encoder

        # Prefer hardware when user asked for it, or when MP4 is already selected
        prefer_hw = bool(settings.hardware_encode) or settings.wants_mp4()
        settings.h264_encoder = probe_h264_encoder(prefer_hardware=prefer_hw)
        # If VAAPI is present, treat hardware encode as available for MP4 path
        if settings.h264_encoder == "vaapi":
            settings.hardware_encode = True
    except Exception as exc:
        settings.h264_encoder = "none"
        print(f"record: h264 probe failed: {exc}", flush=True)

    pipeline = FramePipeline(settings)
    pipeline.start()
    print(
        f"UI={args.ui} mirror={settings.mirror} demo={settings.allow_demo_without_kinect} "
        f"led_green={settings.led_green} auto_level={settings.auto_level} "
        f"hide_cursor={settings.hide_cursor} {settings.perf_summary()}",
        flush=True,
    )
    print(
        f"record: format={settings.record_format} h264={settings.h264_encoder or 'none'} "
        f"(mp4 opt-in: --mp4 / SLS_RECORD_MP4=1; default remains avi)",
        flush=True,
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
