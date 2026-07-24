"""Subprocess that owns libfreenect (isolate GPF on USB unplug — #16).

Protocol (binary on stdout; JSON lines on stdin):

Parent → worker (stdin, one JSON object per line)::
  {"cmd":"open","index":0,"led":1,"auto_level":true,"tilt":0,"ir":50}
  {"cmd":"led","state":2}
  {"cmd":"stop"}
  {"cmd":"ping"}

Worker → parent (stdout binary frames)::
  Header 9 bytes: magic b'SLFK' (4) + type u8 (1) + payload_len u32 BE (4)
  Types: FRAME=1 OK=2 ERR=3 DEAD=4 PONG=5
  FRAME payload: depth uint16 LE 640×480 + IR uint8 640×480
"""

from __future__ import annotations

import json
import select
import struct
import sys
import time
import traceback

# Only this process should load freenect / libusb heavily
from .freenect_io import (  # noqa: E402
    DEPTH_H,
    DEPTH_W,
    FreenectError,
    FreenectNative,
    LED_GREEN,
    LED_OFF,
)

MAGIC = b"SLFK"
TYPE_FRAME = 1
TYPE_OK = 2
TYPE_ERR = 3
TYPE_DEAD = 4
TYPE_PONG = 5

_HDR = struct.Struct("!4sBI")  # magic, type, payload_len
DEPTH_BYTES = DEPTH_W * DEPTH_H * 2
IR_BYTES = DEPTH_W * DEPTH_H
FRAME_BYTES = DEPTH_BYTES + IR_BYTES


def _write_msg(msg_type: int, payload: bytes = b"") -> None:
    sys.stdout.buffer.write(_HDR.pack(MAGIC, msg_type, len(payload)))
    if payload:
        sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _write_err(msg: str) -> None:
    _write_msg(TYPE_ERR, msg.encode("utf-8", errors="replace")[:500])


def _write_ok(msg: str = "ok") -> None:
    _write_msg(TYPE_OK, msg.encode("utf-8", errors="replace")[:200])


def _read_cmds(timeout: float = 0.0) -> list:
    """Non-blocking line reads from stdin."""
    out = []
    try:
        r, _, _ = select.select([sys.stdin], [], [], timeout)
    except (ValueError, OSError):
        return out
    if not r:
        return out
    # Drain available lines without blocking forever
    while True:
        try:
            r2, _, _ = select.select([sys.stdin], [], [], 0)
        except (ValueError, OSError):
            break
        if not r2:
            break
        line = sys.stdin.readline()
        if line == "":
            # EOF — parent closed
            out.append({"cmd": "stop"})
            break
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            _write_err(f"bad json: {line[:80]}")
    return out


def main() -> int:
    # Unbuffered binary stdout for frames
    try:
        sys.stdout.reconfigure(encoding=None)  # type: ignore[attr-defined]
    except Exception:
        pass

    kinect: FreenectNative | None = None
    running = True

    while running:
        cmds = _read_cmds(timeout=0.05 if kinect is None else 0.0)
        for cmd in cmds:
            c = (cmd.get("cmd") or "").lower()
            if c == "ping":
                _write_msg(TYPE_PONG, b"pong")
            elif c == "stop":
                running = False
                break
            elif c == "led" and kinect is not None:
                try:
                    kinect.set_led(int(cmd.get("state", LED_GREEN)))
                    _write_ok("led")
                except Exception as e:
                    _write_err(f"led: {e}")
            elif c == "open":
                if kinect is not None:
                    try:
                        kinect.stop()
                    except Exception:
                        pass
                    kinect = None
                try:
                    k = FreenectNative(
                        index=int(cmd.get("index", 0)),
                        led=int(cmd.get("led", LED_GREEN)),
                        tilt_degs=int(cmd.get("tilt", 0)),
                        auto_level=bool(cmd.get("auto_level", True)),
                        ir_brightness=int(cmd.get("ir", 50)),
                    )
                    k.prepare()
                    kinect = k
                    _write_ok("open")
                except FreenectError as e:
                    kinect = None
                    _write_err(str(e))
                except Exception as e:
                    kinect = None
                    _write_err(f"open: {e}")
                    traceback.print_exc(file=sys.stderr)
            elif c == "close":
                if kinect is not None:
                    try:
                        kinect.stop()
                    except Exception:
                        pass
                    kinect = None
                _write_ok("close")

        if not running:
            break

        if kinect is None:
            continue

        try:
            if kinect.is_dead():
                reason = kinect.dead_reason() or "device dead"
                _write_msg(TYPE_DEAD, reason.encode("utf-8", errors="replace")[:300])
                try:
                    kinect.stop()
                except Exception:
                    pass
                kinect = None
                continue
            depth, ir = kinect.get_depth_and_ir()
            d = np_as_le_u16(depth)
            i = np_as_u8(ir)
            if len(d) != DEPTH_BYTES or len(i) != IR_BYTES:
                _write_err(
                    f"bad frame size depth={len(d)} ir={len(i)} "
                    f"want {DEPTH_BYTES}+{IR_BYTES}"
                )
                continue
            _write_msg(TYPE_FRAME, d + i)
        except FreenectError as e:
            _write_msg(TYPE_DEAD, str(e).encode("utf-8", errors="replace")[:300])
            try:
                kinect.stop()
            except Exception:
                pass
            kinect = None
        except Exception as e:
            # Do not let Python exceptions kill without notice
            _write_msg(
                TYPE_DEAD,
                f"worker: {e}".encode("utf-8", errors="replace")[:300],
            )
            try:
                kinect.stop()
            except Exception:
                pass
            kinect = None
            time.sleep(0.05)

    if kinect is not None:
        try:
            kinect.set_led(LED_OFF)
        except Exception:
            pass
        try:
            kinect.stop()
        except Exception:
            pass
    return 0


def np_as_le_u16(arr) -> bytes:
    import numpy as np

    a = np.ascontiguousarray(arr, dtype=np.uint16)
    if a.shape != (DEPTH_H, DEPTH_W):
        a = a.reshape(DEPTH_H, DEPTH_W)
    return a.tobytes()  # native LE on x86


def np_as_u8(arr) -> bytes:
    import numpy as np

    a = np.ascontiguousarray(arr, dtype=np.uint8)
    if a.shape != (DEPTH_H, DEPTH_W):
        a = a.reshape(DEPTH_H, DEPTH_W)
    return a.tobytes()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        try:
            _write_err("worker fatal")
        except Exception:
            pass
        raise SystemExit(1)
