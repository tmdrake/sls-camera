"""Depth and IR visualization helpers."""

from __future__ import annotations

import cv2
import numpy as np


def colorize_depth(
    depth_u16: np.ndarray,
    dmin: int = 500,
    dmax: int = 4500,
) -> np.ndarray:
    """Map 11-bit Kinect depth to a TURBO colormap BGR image."""
    d = depth_u16.astype(np.float32)
    valid = (d > 0) & (d < 2047)
    scaled = np.zeros_like(d, dtype=np.float32)
    if valid.any():
        vals = d[valid]
        lo = float(np.percentile(vals, 5))
        hi = float(np.percentile(vals, 95))
        if hi <= lo:
            hi = lo + 1.0
        scaled[valid] = np.clip((d[valid] - lo) / (hi - lo), 0.0, 1.0)

    gray = (scaled * 255.0).astype(np.uint8)
    color = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)
    color[~valid] = (0, 0, 0)
    return color


def ir_to_bgr(ir_u8: np.ndarray) -> np.ndarray:
    """IR grayscale → display BGR with contrast for the PiP."""
    if ir_u8.ndim == 3:
        return ir_u8.copy()
    # CLAHE helps when IR sensor image is dark
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    eq = clahe.apply(ir_u8)
    return cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR)


def ir_for_pose(ir_u8: np.ndarray) -> np.ndarray:
    """
    Preprocess IR into a 3-channel image MediaPipe is more likely to accept.
    (MediaPipe is trained on RGB photos; raw IR is a poor match.)
    """
    if ir_u8.ndim == 3:
        gray = cv2.cvtColor(ir_u8, cv2.COLOR_BGR2GRAY)
    else:
        gray = ir_u8
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    # Pseudo-color body mass often detects better than flat gray
    return cv2.applyColorMap(eq, cv2.COLORMAP_BONE)


def maybe_flip(img: np.ndarray, mirror: bool) -> np.ndarray:
    if mirror:
        return cv2.flip(img, 1)
    return img
