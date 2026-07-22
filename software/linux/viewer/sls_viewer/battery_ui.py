"""Qt battery gauge pixmap for the field status bar (#12).

Keeps ``battery.py`` free of Qt. Hidden when no system battery.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .battery import LOW_PERCENT, BatteryReading


def gauge_colors(reading: BatteryReading) -> Tuple[str, str, str]:
    """Return (outline, fill, text) hex colors for the current state."""
    p = int(reading.percent or 0)
    if reading.charging:
        return ("#00ffb4", "#00aaff", "#e0ffff")
    if p <= LOW_PERCENT:
        return ("#ff6666", "#ff3333", "#ffaaaa")
    if p <= 30:
        return ("#ffaa44", "#ff9900", "#ffddaa")
    return ("#00ffb4", "#00cc88", "#c8ffe8")


def battery_gauge_pixmap(
    reading: BatteryReading,
    *,
    height: int = 36,
) -> Optional["object"]:
    """Build a glanceable battery icon + percent for the status bar.

    Returns ``None`` when no battery (caller should hide the widget).
    """
    if not reading.present or reading.percent is None:
        return None

    try:
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import (
            QColor,
            QFont,
            QPainter,
            QPen,
            QPixmap,
            QPolygonF,
        )
    except Exception:
        return None

    p = max(0, min(100, int(reading.percent)))
    outline_hex, fill_hex, text_hex = gauge_colors(reading)
    outline = QColor(outline_hex)
    fill = QColor(fill_hex)
    text_c = QColor(text_hex)

    # Layout: [ icon body ][ % text ]  — tall enough for tablet glance
    h = max(28, int(height))
    icon_h = h - 6
    icon_w = int(icon_h * 1.85)
    text_w = 52
    pad = 4
    w = icon_w + text_w + pad * 2
    pix = QPixmap(w, h)
    pix.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Battery body (left) + terminal nub (right)
    body_x = float(pad)
    body_y = float((h - icon_h) / 2)
    body_w = float(icon_w - 8)
    body_h = float(icon_h)
    nub_w = 5.0
    nub_h = body_h * 0.42
    radius = 4.0

    body = QRectF(body_x, body_y, body_w, body_h)
    painter.setPen(QPen(outline, 2.0))
    painter.setBrush(QColor(10, 20, 16, 220))
    painter.drawRoundedRect(body, radius, radius)

    nub = QRectF(
        body_x + body_w,
        body_y + (body_h - nub_h) / 2,
        nub_w,
        nub_h,
    )
    painter.setBrush(outline)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(nub, 1.5, 1.5)

    # Fill level (inset)
    inset = 3.0
    fill_max_w = body_w - 2 * inset
    fill_w = fill_max_w * (p / 100.0)
    if fill_w > 0.5:
        fill_rect = QRectF(
            body_x + inset,
            body_y + inset,
            fill_w,
            body_h - 2 * inset,
        )
        painter.setBrush(fill)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(fill_rect, 2.0, 2.0)

    # Charging bolt (white/cyan on fill)
    if reading.charging:
        cx = body_x + body_w * 0.5
        cy = body_y + body_h * 0.5
        bolt = QPolygonF(
            [
                QPointF(cx + 2, cy - body_h * 0.32),
                QPointF(cx - 6, cy + 1),
                QPointF(cx - 1, cy + 1),
                QPointF(cx - 3, cy + body_h * 0.32),
                QPointF(cx + 6, cy - 1),
                QPointF(cx + 1, cy - 1),
            ]
        )
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#003344"), 0.8))
        painter.drawPolygon(bolt)

    # Low: thin red edge flash already via outline color; bang optional
    # Percent text to the right of the icon
    font = QFont()
    font.setBold(True)
    font.setPixelSize(max(12, int(h * 0.42)))
    painter.setFont(font)
    painter.setPen(text_c)
    label = f"{p}%"
    if reading.charging:
        label = f"{p}%"  # bolt already on icon
    text_rect = QRectF(body_x + body_w + nub_w + 4, 0, text_w, h)
    painter.drawText(
        text_rect,
        int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        label,
    )

    painter.end()
    return pix


def battery_tooltip(reading: BatteryReading) -> str:
    """Hover / accessibility detail for the gauge."""
    if not reading.present or reading.percent is None:
        return ""
    p = max(0, min(100, int(reading.percent)))
    st = (reading.status or "").strip() or ("charging" if reading.charging else "battery")
    name = (reading.name or "").strip()
    bits = [f"Battery {p}%", st]
    if reading.charging:
        bits.append("charging / on AC")
    elif p <= LOW_PERCENT:
        bits.append("LOW")
    if name:
        bits.append(name)
    return " · ".join(bits)
