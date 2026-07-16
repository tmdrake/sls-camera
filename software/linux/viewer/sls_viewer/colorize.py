"""Depth and IR visualization helpers."""

from __future__ import annotations

import cv2
import numpy as np


def colorize_depth(
    depth_u16: np.ndarray,
    dmin: int = 500,
    dmax: int = 4500,
) -> np.ndarray:
    """
    Map 11-bit Kinect depth to a TURBO colormap BGR image.
    Invalid / too-far pixels stay near black.
    """
    d = depth_u16.astype(np.float32)
    # 11-bit raw: 0 and 2047 often invalid
    valid = (d > 0) & (d < 2047)
    # Approximate: use raw as distance rank if not mm mode
    scaled = np.zeros_like(d, dtype=np.float32)
    if valid.any():
        # Stretch valid depths into 0..1 using percentile for robustness
        vals = d[valid]
        lo = max(float(np.percentile(vals, 5)), float(dmin) / 10.0)
        hi = min(float(np.percentile(vals, 95)), float(dmax) / 2.0)
        if hi <= lo:
            hi = lo + 1.0
        scaled[valid] = np.clip((d[valid] - lo) / (hi - lo), 0.0, 1.0)

    gray = (scaled * 255.0).astype(np.uint8)
    color = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)
    color[~valid] = (0, 0, 0)
    return color


def ir_to_bgr(ir_u8: np.ndarray) -> np.ndarray:
    """IR grayscale → BGR with gentle contrast for skeleton visibility."""
    if ir_u8.ndim == 3:
        return ir_u8.copy()
    # Normalize histogram a bit
    norm = cv2.normalize(ir_u8, None, 0, 255, cv2.NORM_MINMAX)
    eq = cv2.equalizeHist(norm)
    return cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR)


def maybe_flip(img: np.ndarray, mirror: bool) -> np.ndarray:
    if mirror:
        return cv2.flip(img, 1)
    return img
