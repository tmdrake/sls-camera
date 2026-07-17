"""Draw SLS-style stick figures on BGR images."""

from __future__ import annotations

from typing import List, Sequence, Tuple

import cv2
import numpy as np

from .pose import POSE_BONES, POSE_JOINTS


def draw_skeletons(
    image_bgr: np.ndarray,
    poses: Sequence[Sequence[Tuple[float, float, float]]],
    bone_color: Tuple[int, int, int] = (0, 255, 180),
    joint_color: Tuple[int, int, int] = (0, 255, 255),
    bone_thickness: int = 3,
    joint_radius: int = 5,
    min_vis: float = 0.20,
) -> np.ndarray:
    out = image_bgr
    for pose in poses:
        if not pose:
            continue
        # bones
        for a, b in POSE_BONES:
            if a >= len(pose) or b >= len(pose):
                continue
            xa, ya, va = pose[a]
            xb, yb, vb = pose[b]
            if va < min_vis or vb < min_vis:
                continue
            cv2.line(
                out,
                (int(xa), int(ya)),
                (int(xb), int(yb)),
                bone_color,
                bone_thickness,
                cv2.LINE_AA,
            )
        # joints
        for j in POSE_JOINTS:
            if j >= len(pose):
                continue
            x, y, v = pose[j]
            if v < min_vis:
                continue
            cv2.circle(out, (int(x), int(y)), joint_radius, joint_color, -1, cv2.LINE_AA)
            cv2.circle(out, (int(x), int(y)), joint_radius + 2, (0, 0, 0), 1, cv2.LINE_AA)
    return out


def scale_poses(
    poses: Sequence[Sequence[Tuple[float, float, float]]],
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> List[List[Tuple[float, float, float]]]:
    if src_w == dst_w and src_h == dst_h:
        return [list(p) for p in poses]
    sx = dst_w / float(src_w)
    sy = dst_h / float(src_h)
    out: List[List[Tuple[float, float, float]]] = []
    for pose in poses:
        out.append([(x * sx, y * sy, v) for x, y, v in pose])
    return out
