"""Native Qt fullscreen always-on-top SLS window."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .backlight import (
    DEFAULT_STEP as BRIGHTNESS_STEP,
    get_brightness,
    nudge_brightness,
    apply_persisted_percent,
)
from . import freenect_io
from .battery import BatteryMonitor
from .drakevox import DrakeVoxEngine, paint_drakevox_bgr
from .display_inhibit import DisplayInhibit
from .host_power import EXIT_OK, EXIT_POWEROFF
from .media_format import (
    DEFAULT_LABEL,
    device_size_bytes,
    format_volume_fat32,
    list_format_candidates,
)
from .session_io import AUDIO_SAMPLE_RATE, SessionRecorder
from .spectrum import (
    SpectrumAnalyzer,
    next_spectrum_style,
    spectrum_style_label,
)
from .tts import DrakeVoxTTS, backend_name as tts_backend_name

if TYPE_CHECKING:
    from .pipeline import FramePipeline

_STYLE = """
QMainWindow, QWidget, QDialog {
    background-color: #000000; color: #c8c8c8;
}
QLabel#video { background-color: #000000; }
QLabel#spectrum { background-color: #0c0c0c; }
QLabel#status {
    color: #aaaaaa; font-size: 13px; padding: 4px 8px;
}
QLabel#title {
    color: #00ffb4; font-size: 16px; font-weight: 700;
    letter-spacing: 2px; padding: 4px 8px;
}
QLabel#hdr {
    color: #00ffb4; font-size: 15px; font-weight: 700;
    padding: 4px 0 10px 0;
}
QLabel#vallabel {
    color: #00ffb4; font-size: 14px; font-weight: 600;
    min-width: 80px;
}
QPushButton {
    min-height: 44px; min-width: 48px;
    background-color: rgba(0, 40, 30, 220);
    color: #00ffb4; border: 1px solid #00ffb4;
    border-radius: 8px; font-size: 14px; font-weight: 600;
    padding: 6px 12px;
}
QPushButton#wide {
    min-width: 100px;
}
QPushButton:pressed { background-color: rgba(0, 80, 60, 240); }
QDialog {
    border: 1px solid #00ffb4;
}
/* Settings pane: ~10% shorter controls so left column needs less scroll.
   Cap height (max-height) so size-hints cannot inflate past the target. */
QDialog QPushButton {
    min-height: 36px;
    max-height: 40px;
    min-width: 40px;
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 6px;
}
QDialog QPushButton#wide {
    min-width: 80px;
}
QDialog QLabel#vallabel {
    font-size: 12px;
    min-width: 56px;
}
QDialog QLabel#hdr {
    font-size: 14px;
    padding: 2px 0 4px 0;
}
QMessageBox {
    background-color: #000000; color: #c8c8c8;
}
QMessageBox QLabel {
    color: #c8c8c8; font-size: 14px;
}
QMessageBox QPushButton {
    min-height: 40px; min-width: 88px;
    background-color: rgba(0, 40, 30, 220);
    color: #00ffb4; border: 1px solid #00ffb4;
    border-radius: 8px; font-size: 14px; font-weight: 600;
    padding: 6px 14px;
}
QScrollArea {
    border: none;
    background-color: #000000;
}
QScrollBar:vertical {
    width: 18px;
    background: #0a1210;
    margin: 2px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #00aa78;
    min-height: 40px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #00ffb4; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


def bgr_to_qpixmap(bgr: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def format_display_geometry(app: Optional[QApplication] = None) -> str:
    """One-line primary-screen geometry for logs / hardware matrix (#6)."""
    app = app or QApplication.instance()
    if app is None:
        return "display: (no QApplication)"
    screen = app.primaryScreen()
    if screen is None:
        screens = app.screens()
        screen = screens[0] if screens else None
    if screen is None:
        return "display: (no screen)"
    g = screen.geometry()
    avail = screen.availableGeometry()
    dpr = float(screen.devicePixelRatio())
    try:
        dpi = float(screen.logicalDotsPerInch())
    except Exception:
        dpi = 0.0
    orient = ""
    try:
        o = screen.orientation()
        name = getattr(o, "name", None)
        if callable(name):
            orient = f" orient={o.name}"
        else:
            orient = f" orient={int(o)}"
    except Exception:
        pass
    return (
        f"display: {g.width()}x{g.height()} "
        f"avail={avail.width()}x{avail.height()} "
        f"dpr={dpr:.1f} dpi={dpi:.0f}{orient}"
    )


def log_display_geometry(app: Optional[QApplication] = None) -> str:
    """Print geometry once to stdout; return the same line."""
    line = format_display_geometry(app)
    print(line, flush=True)
    return line


class SettingsDialog(QDialog):
    """Field Settings: horizontal two-pane layout for landscape tablets.

    Left  — controls (pose, spectrum, DrakeVox, captures, actions)
    Right — status / log (display geometry, mic, DrakeVox history, keys)

    Height/width capped to ~90% of availableGeometry; left pane scrolls if needed (#6).
    """

    def __init__(
        self,
        pipeline: FramePipeline,
        spectrum: SpectrumAnalyzer,
        session: SessionRecorder,
        drakevox: DrakeVoxEngine,
        parent=None,
    ):
        super().__init__(parent)
        self.pipeline = pipeline
        self.spectrum = spectrum
        self.session = session
        self.drakevox = drakevox
        self.setWindowTitle("Settings")
        self.setModal(False)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(_STYLE)
        self.setMinimumWidth(640)
        self.setMinimumHeight(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        # Header
        top = QHBoxLayout()
        hdr = QLabel("SETTINGS")
        hdr.setObjectName("hdr")
        top.addWidget(hdr)
        top.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("wide")
        self.btn_close.clicked.connect(self.accept)
        top.addWidget(self.btn_close)
        root.addLayout(top)

        # Main: left controls | right status/log
        panes = QHBoxLayout()
        panes.setSpacing(12)

        # ----- LEFT: controls (scroll if short) -----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        left = QWidget()
        left.setStyleSheet("background-color: #000000;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(6)

        left_title = QLabel("Controls")
        left_title.setStyleSheet("color: #00ffb4; font-size: 12px; font-weight: 600;")
        left_layout.addWidget(left_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        step = pipeline.s.pose_conf_step
        row = 0

        def _add_toggle_row(label: str, btn: QPushButton) -> None:
            nonlocal row
            grid.addWidget(QLabel(label), row, 0)
            btn.setObjectName("wide")
            grid.addWidget(btn, row, 1, 1, 3)
            row += 1

        # Max people
        grid.addWidget(QLabel("Max people"), row, 0)
        self.btn_max_down = QPushButton("−")
        self.btn_max_down.clicked.connect(lambda: self._nudge_max(-1))
        self.max_label = QLabel()
        self.max_label.setObjectName("vallabel")
        self.max_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_max_up = QPushButton("+")
        self.btn_max_up.clicked.connect(lambda: self._nudge_max(+1))
        grid.addWidget(self.btn_max_down, row, 1)
        grid.addWidget(self.max_label, row, 2)
        grid.addWidget(self.btn_max_up, row, 3)
        row += 1

        # Confidence
        grid.addWidget(QLabel("Confidence"), row, 0)
        self.btn_conf_down = QPushButton("−")
        self.btn_conf_down.clicked.connect(lambda: self._nudge_conf(-step))
        self.conf_label = QLabel()
        self.conf_label.setObjectName("vallabel")
        self.conf_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_conf_up = QPushButton("+")
        self.btn_conf_up.clicked.connect(lambda: self._nudge_conf(+step))
        grid.addWidget(self.btn_conf_down, row, 1)
        grid.addWidget(self.conf_label, row, 2)
        grid.addWidget(self.btn_conf_up, row, 3)
        row += 1

        self.btn_mirror = QPushButton()
        self.btn_mirror.clicked.connect(self._toggle_mirror)
        _add_toggle_row("Mirror", self.btn_mirror)

        self.btn_spectrum = QPushButton()
        self.btn_spectrum.clicked.connect(self._toggle_spectrum)
        _add_toggle_row("Spectrum", self.btn_spectrum)

        self.btn_spectrum_style = QPushButton()
        self.btn_spectrum_style.setObjectName("wide")
        self.btn_spectrum_style.setToolTip(
            "Cycle spectrum strip look. Default is Phosphor (scope trail). "
            "Saved across restarts. Defaults button restores Phosphor."
        )
        self.btn_spectrum_style.clicked.connect(self._cycle_spectrum_style)
        _add_toggle_row("Spectrum style", self.btn_spectrum_style)

        self.btn_autosnap = QPushButton()
        self.btn_autosnap.clicked.connect(self._toggle_autosnap)
        _add_toggle_row("Auto-snap on detect", self.btn_autosnap)

        self.btn_drakevox = QPushButton()
        self.btn_drakevox.setToolTip(
            "ON: show panel + generate words (timer/TTS) · OFF: hide panel and stop generation"
        )
        self.btn_drakevox.clicked.connect(self._toggle_drakevox)
        _add_toggle_row("DrakeVox", self.btn_drakevox)

        self.btn_drakevox_autosnap = QPushButton()
        self.btn_drakevox_autosnap.setToolTip(
            "When ON: auto-snap on detect also fires DrakeVox (word + TTS in the JPEG). "
            "Manual Snap does not force a new word."
        )
        self.btn_drakevox_autosnap.clicked.connect(self._toggle_drakevox_autosnap)
        _add_toggle_row("DrakeVox on auto-snap", self.btn_drakevox_autosnap)

        # Brightness
        grid.addWidget(QLabel("Brightness"), row, 0)
        self.btn_bright_down = QPushButton("−")
        self.btn_bright_down.setToolTip("Dimmer (−10%)")
        self.btn_bright_down.clicked.connect(
            lambda: self._nudge_brightness(-BRIGHTNESS_STEP)
        )
        self.bright_label = QLabel()
        self.bright_label.setObjectName("vallabel")
        self.bright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_bright_up = QPushButton("+")
        self.btn_bright_up.setToolTip("Brighter (+10%)")
        self.btn_bright_up.clicked.connect(
            lambda: self._nudge_brightness(+BRIGHTNESS_STEP)
        )
        grid.addWidget(self.btn_bright_down, row, 1)
        grid.addWidget(self.bright_label, row, 2)
        grid.addWidget(self.btn_bright_up, row, 3)
        row += 1

        self.btn_captures = QPushButton()
        self.btn_captures.setToolTip(
            "Auto (default) = USB/SD if mounted → sls-captures/ on that media; "
            "else local viewer/captures. Local = always viewer/captures. "
            "New snaps/recordings follow this setting; use Copy local→media "
            "to move existing local files onto a stick/card."
        )
        self.btn_captures.clicked.connect(self._toggle_captures_target)
        _add_toggle_row("Captures to", self.btn_captures)

        left_layout.addLayout(grid)

        # Actions 2×2 under controls
        act = QGridLayout()
        act.setHorizontalSpacing(6)
        act.setVerticalSpacing(6)
        self.btn_defaults = QPushButton("Defaults")
        self.btn_defaults.setObjectName("wide")
        self.btn_defaults.setToolTip(
            "Reset Max people=1, Confidence=0.5, Captures to Auto, "
            "and Spectrum style to Phosphor"
        )
        self.btn_defaults.clicked.connect(self._reset_defaults)
        self.btn_clear_captures = QPushButton("Clear captures")
        self.btn_clear_captures.setObjectName("wide")
        self.btn_clear_captures.setToolTip(
            "Delete files in the current captures folder (local or media/sls-captures/)"
        )
        self.btn_clear_captures.clicked.connect(self._clear_captures)
        self.btn_copy_to_media = QPushButton("Copy local→media")
        self.btn_copy_to_media.setObjectName("wide")
        self.btn_copy_to_media.setToolTip(
            "Copy existing viewer/captures files onto the mounted USB/SD "
            "(into sls-captures/). Does not delete local files. "
            "Use when you shot to local first, then plug in a stick/card."
        )
        self.btn_copy_to_media.clicked.connect(self._copy_local_to_media)
        self.btn_drakevox_now = QPushButton("DrakeVox now")
        self.btn_drakevox_now.setObjectName("wide")
        self.btn_drakevox_now.setToolTip(
            "Speak a word now (requires DrakeVox ON; recorded if REC is active)"
        )
        self.btn_drakevox_now.clicked.connect(self._drakevox_now)
        act.addWidget(self.btn_defaults, 0, 0)
        act.addWidget(self.btn_clear_captures, 0, 1)
        act.addWidget(self.btn_copy_to_media, 1, 0)
        act.addWidget(self.btn_drakevox_now, 1, 1)
        left_layout.addLayout(act)

        # Format USB/SD for field captures (#8) — only button; no separate Prepare
        self.btn_format_media = QPushButton("Format removable media…")
        self.btn_format_media.setObjectName("wide")
        self.btn_format_media.setToolTip(
            "ERASE the mounted USB stick or SD card, then format for SLS "
            "(FAT32, label SLS-MEDIA, folder sls-captures/). "
            "Two confirmations. Needs admin (pkexec/sudo). "
            "Hidden when no stick/card is mounted."
        )
        self.btn_format_media.clicked.connect(self._format_media)
        left_layout.addWidget(self.btn_format_media)
        left_layout.addStretch(1)

        self._scroll.setWidget(left)
        panes.addWidget(self._scroll, stretch=3)

        # ----- RIGHT: status / log pane -----
        right = QFrame()
        right.setObjectName("statusPane")
        right.setStyleSheet(
            "QFrame#statusPane {"
            "  background-color: #0a1210;"
            "  border: 1px solid #1a4030;"
            "  border-radius: 8px;"
            "}"
        )
        right.setMinimumWidth(240)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 10, 12, 10)
        right_layout.setSpacing(8)

        right_title = QLabel("Status / log")
        right_title.setStyleSheet("color: #00ffb4; font-size: 12px; font-weight: 600;")
        right_layout.addWidget(right_title)

        self.display_label = QLabel("")
        self.display_label.setStyleSheet(
            "color: #88ccaa; font-size: 11px; font-family: monospace;"
        )
        self.display_label.setWordWrap(True)
        self.display_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        right_layout.addWidget(self.display_label)

        self.mic_label = QLabel("")
        self.mic_label.setStyleSheet("color: #888; font-size: 11px;")
        self.mic_label.setWordWrap(True)
        right_layout.addWidget(self.mic_label)

        self.drakevox_label = QLabel("")
        self.drakevox_label.setStyleSheet("color: #00ffb4; font-size: 12px;")
        self.drakevox_label.setWordWrap(True)
        right_layout.addWidget(self.drakevox_label)

        # Longer word history (up to 24); scroll within the status pane
        hist_scroll = QScrollArea()
        hist_scroll.setWidgetResizable(True)
        hist_scroll.setFrameShape(QFrame.Shape.NoFrame)
        hist_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        hist_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        hist_scroll.setStyleSheet("background-color: transparent;")
        self.drakevox_history = QLabel("")
        self.drakevox_history.setStyleSheet(
            "color: #888; font-size: 11px; font-family: monospace;"
            " background-color: transparent;"
        )
        self.drakevox_history.setWordWrap(True)
        self.drakevox_history.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.drakevox_history.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        hist_scroll.setWidget(self.drakevox_history)
        right_layout.addWidget(hist_scroll, stretch=1)

        hint = QLabel(
            "Keys: [ ] conf  ·  , . max  ·  M mirror  ·  O DrakeVox  ·  S settings  ·  Esc close"
        )
        hint.setStyleSheet("color: #555; font-size: 10px;")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        panes.addWidget(right, stretch=2)
        root.addLayout(panes, stretch=1)

        self._refresh()

    def _refresh(self) -> None:
        self.max_label.setText(f"{self.pipeline.max_poses}")
        self.conf_label.setText(f"{self.pipeline.pose_confidence:.2f}")
        self.btn_mirror.setText("ON" if self.pipeline.mirror else "OFF")
        self.btn_spectrum.setText(
            "ON" if self.pipeline.s.spectrum_enabled else "OFF"
        )
        self.btn_spectrum_style.setText(
            spectrum_style_label(self.pipeline.s.spectrum_style)
        )
        self.btn_autosnap.setText(
            "ON" if self.pipeline.s.auto_snap_on_detect else "OFF"
        )
        on = bool(self.pipeline.s.drakevox_enabled)
        self.btn_drakevox.setText("ON" if on else "OFF")
        self.btn_drakevox_now.setEnabled(on)
        self.btn_drakevox_autosnap.setText(
            "ON" if self.pipeline.s.drakevox_on_autosnap else "OFF"
        )
        self.btn_drakevox_autosnap.setEnabled(on)

        bri = get_brightness()
        if bri.available and bri.percent is not None:
            self.bright_label.setText(f"{bri.percent}%")
            can = bool(bri.writable)
            self.btn_bright_down.setEnabled(can)
            self.btn_bright_up.setEnabled(can)
            tip = bri.backend
            if bri.detail:
                tip = f"{tip} — {bri.detail}"
            self.bright_label.setToolTip(tip)
            self.btn_bright_down.setToolTip(tip)
            self.btn_bright_up.setToolTip(tip)
        else:
            self.bright_label.setText("n/a")
            self.btn_bright_down.setEnabled(False)
            self.btn_bright_up.setEnabled(False)
            tip = bri.detail or "no brightness control on this display"
            self.bright_label.setToolTip(tip)

        # Right-pane display geometry (from parent cache or live probe)
        parent = self.parent()
        geom = ""
        if parent is not None:
            geom = str(getattr(parent, "_display_geometry_line", "") or "")
        if not geom:
            geom = format_display_geometry()
        inh = ""
        if parent is not None and hasattr(parent, "display_inhibit"):
            di = parent.display_inhibit
            if di is not None and di.active:
                inh = f"\nwake-lock: {di.detail}"
            else:
                inh = "\nwake-lock: (not active)"
        self.display_label.setText(geom + inh)

        cap_mode = self.pipeline.s.captures_target
        has_media = False
        if parent is not None and hasattr(parent, "session"):
            label = parent.session.captures_label
            has_media = parent.session.has_removable_media()
            if cap_mode == "auto":
                self.btn_captures.setText(f"Auto · {label}")
            else:
                self.btn_captures.setText("Local")
            self.btn_captures.setEnabled(not parent.session.recording)
            # Only show Copy when USB/SD is mounted (nothing to copy to otherwise)
            self.btn_copy_to_media.setVisible(has_media)
            self.btn_copy_to_media.setEnabled(
                has_media and not parent.session.recording
            )
            rec = bool(parent.session.recording)
            can_fmt = False
            if has_media and not rec:
                for _vol, ok, _why in list_format_candidates():
                    if ok:
                        can_fmt = True
                        break
            self.btn_format_media.setVisible(has_media)
            self.btn_format_media.setEnabled(can_fmt)
        else:
            self.btn_captures.setText(
                "Auto" if cap_mode == "auto" else "Local"
            )
            self.btn_copy_to_media.setVisible(False)
            self.btn_copy_to_media.setEnabled(False)
            self.btn_format_media.setVisible(False)
            self.btn_format_media.setEnabled(False)

        mic = self.spectrum.device_name or "(no mic)"
        err = self.spectrum.error
        if self.spectrum.active:
            self.mic_label.setText(f"Mic: {mic}")
        elif err:
            self.mic_label.setText(f"Mic: off — {err[:80]}")
        else:
            self.mic_label.setText(
                "Mic: off — install kinect-audio-setup for Kinect array, or use system mic"
            )
        if self.pipeline.s.drakevox_enabled:
            hist0 = self.drakevox.history()
            tts = tts_backend_name()
            bank = self.drakevox.word_source
            if hist0:
                self.drakevox_label.setText(
                    f"DrakeVox: {hist0[0].label()}  ·  {bank}  ·  TTS: {tts}"
                )
            else:
                self.drakevox_label.setText(
                    f"DrakeVox: (waiting)  ·  {bank}  ·  TTS: {tts}"
                )
        else:
            self.drakevox_label.setText(
                f"DrakeVox: off  ·  {self.drakevox.word_source}"
            )
        # Right pane is taller with two-pane layout — show more words (was 8)
        hist = self.drakevox.history_lines(24)
        self.drakevox_history.setText(
            "History:\n" + "\n".join(hist) if hist else "History: (none yet)"
        )

    def _nudge_conf(self, delta: float) -> None:
        self.pipeline.adjust_pose_confidence(delta)
        self._refresh()

    def _nudge_max(self, delta: int) -> None:
        self.pipeline.adjust_max_poses(delta)
        self._refresh()

    def _toggle_mirror(self) -> None:
        self.pipeline.mirror = not self.pipeline.mirror
        self._refresh()

    def _toggle_spectrum(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "set_spectrum_enabled"):
            parent.set_spectrum_enabled(not self.pipeline.s.spectrum_enabled)
        self._refresh()

    def _cycle_spectrum_style(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "cycle_spectrum_style"):
            parent.cycle_spectrum_style()
        self._refresh()

    def _toggle_autosnap(self) -> None:
        self.pipeline.s.auto_snap_on_detect = not self.pipeline.s.auto_snap_on_detect
        self.pipeline.s.save_persisted()
        self._refresh()

    def _toggle_drakevox(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "set_drakevox_enabled"):
            parent.set_drakevox_enabled(not self.pipeline.s.drakevox_enabled)
        self._refresh()

    def _toggle_drakevox_autosnap(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "set_drakevox_on_autosnap"):
            parent.set_drakevox_on_autosnap(
                not self.pipeline.s.drakevox_on_autosnap
            )
        self._refresh()

    def _nudge_brightness(self, delta: int) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "nudge_display_brightness"):
            parent.nudge_display_brightness(delta)
        self._refresh()

    def _toggle_captures_target(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "toggle_captures_target"):
            parent.toggle_captures_target()
        self._refresh()

    def _format_media(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "format_removable_media"):
            parent.format_removable_media()
        self._refresh()

    def _drakevox_now(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "drakevox_generate_now"):
            parent.drakevox_generate_now()
        self._refresh()

    def _confirm(self, title: str, text: str, yes_label: str = "OK") -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Question)
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        yes = box.button(QMessageBox.StandardButton.Yes)
        if yes is not None:
            yes.setText(yes_label)
        box.setStyleSheet(_STYLE)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _reset_defaults(self) -> None:
        """Pose MediaPipe defaults + Captures Auto + Phosphor spectrum — confirm first."""
        if not self._confirm(
            "Reset defaults",
            "Reset to field defaults?\n\n"
            "• Max people = 1\n"
            "• Confidence = 0.5\n"
            "• Captures to = Auto (USB/SD if mounted, else local)\n"
            "• Spectrum style = Phosphor",
            yes_label="Reset",
        ):
            return
        parent = self.parent()
        if parent is not None and hasattr(parent, "apply_field_defaults"):
            parent.apply_field_defaults()
        else:
            self.pipeline.reset_pose_defaults()
        self._refresh()

    def _clear_captures(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "clear_captures"):
            parent.clear_captures()
        self._refresh()

    def _copy_local_to_media(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "copy_local_to_media"):
            parent.copy_local_to_media()
        self._refresh()

    def _fit_to_screen(self) -> None:
        """Wide landscape dialog: ~90% available size; left pane scrolls if needed."""
        screen = self.screen()
        if screen is None:
            app = QApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return
        avail = screen.availableGeometry()
        max_h = max(320, int(avail.height() * 0.90))
        max_w = max(640, int(avail.width() * 0.92))
        # Prefer a wide panel (two panes) rather than a tall narrow column
        prefer_w = min(max_w, max(720, int(avail.width() * 0.72)))
        prefer_h = min(max_h, max(420, int(avail.height() * 0.72)))
        self.setMinimumWidth(min(640, max_w))
        self.setMaximumWidth(max_w)
        self.setMaximumHeight(max_h)
        self.resize(prefer_w, prefer_h)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh()
        self._fit_to_screen()
        # Center over parent / available area (wide dialog reads better centered)
        parent = self.parentWidget()
        screen = self.screen()
        if screen is None:
            app = QApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        avail = screen.availableGeometry() if screen is not None else None
        if parent is not None:
            pg = parent.geometry()
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + (pg.height() - self.height()) // 2
        elif avail is not None:
            x = avail.x() + (avail.width() - self.width()) // 2
            y = avail.y() + (avail.height() - self.height()) // 2
        else:
            return
        if avail is not None:
            x = max(avail.x(), min(x, avail.x() + avail.width() - self.width()))
            y = max(avail.y(), min(y, avail.y() + avail.height() - self.height()))
        else:
            x = max(0, x)
            y = max(0, y)
        self.move(int(x), int(y))


class SlsMainWindow(QMainWindow):
    """Fullscreen, always-on-top field UI."""

    def __init__(self, pipeline: FramePipeline):
        super().__init__()
        self.pipeline = pipeline
        self.spectrum = SpectrumAnalyzer(n_bars=pipeline.s.spectrum_bars)
        self.session = SessionRecorder()
        self.drakevox = DrakeVoxEngine(enabled=pipeline.s.drakevox_enabled)
        self.tts = DrakeVoxTTS(sample_rate=AUDIO_SAMPLE_RATE)
        # Mix spoken words into AVI whenever recording
        self.tts.set_record_callback(self.session.inject_tts)
        self.battery = BatteryMonitor(poll_s=5.0)
        self.display_inhibit = DisplayInhibit()
        self._settings_dlg: Optional[SettingsDialog] = None
        self._quit_confirmed = False
        self._app_exit_code = EXIT_OK
        self._media_poll_i = 0
        self._inhibit_refresh_i = 0
        self.setWindowTitle("SLS Camera")
        # Apply saved brightness once (tablet backlight or xrandr software)
        if pipeline.s.display_brightness is not None:
            apply_persisted_percent(pipeline.s.display_brightness)
        # Captures path: local or auto USB/SD
        self.session.set_captures_target(pipeline.s.captures_target)
        self.setStyleSheet(_STYLE)
        # Always hold wake lock while field UI is up (#9) — not a Settings toggle
        self.display_inhibit.start()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video = QLabel()
        self.video.setObjectName("video")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setScaledContents(False)
        self.video.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.video, stretch=1)

        # Always reserve strip height so show/hide never resizes the window
        # (toggling setVisible was shrinking fullscreen and clipping Quit).
        self.spectrum_label = QLabel()
        self.spectrum_label.setObjectName("spectrum")
        self.spectrum_label.setFixedHeight(pipeline.s.spectrum_height)
        self.spectrum_label.setMinimumHeight(pipeline.s.spectrum_height)
        self.spectrum_label.setMaximumHeight(pipeline.s.spectrum_height)
        self.spectrum_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.spectrum_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.spectrum_label)

        bar = QWidget()
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 6, 10, 10)
        bar_layout.setSpacing(8)

        self.title = QLabel("SLS CAMERA")
        self.title.setObjectName("title")
        self.status = QLabel("starting…")
        self.status.setObjectName("status")

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setObjectName("wide")
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_snap = QPushButton("Snap")
        self.btn_snap.setObjectName("wide")
        self.btn_snap.setToolTip("Save current frame (JPEG with timestamp)")
        self.btn_snap.clicked.connect(self._snapshot)
        self.btn_record = QPushButton("Record")
        self.btn_record.setObjectName("wide")
        self.btn_record.setToolTip(
            "Start/stop AVI recording with mic audio (Kinect preferred)"
        )
        self.btn_record.clicked.connect(self._toggle_record)
        self.btn_quit = QPushButton("Quit")
        self.btn_quit.setObjectName("wide")
        self.btn_quit.clicked.connect(self._request_quit)

        bar_layout.addWidget(self.title)
        bar_layout.addWidget(self.status, stretch=1)
        bar_layout.addWidget(self.btn_settings)
        bar_layout.addWidget(self.btn_snap)
        bar_layout.addWidget(self.btn_record)
        bar_layout.addWidget(self.btn_quit)
        layout.addWidget(bar)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        step = pipeline.s.pose_conf_step
        QShortcut(QKeySequence("Escape"), self, activated=self._on_escape)
        QShortcut(QKeySequence("Q"), self, activated=self._request_quit)
        QShortcut(QKeySequence("F"), self, activated=self._force_fullscreen)
        QShortcut(QKeySequence("M"), self, activated=self._toggle_mirror)
        QShortcut(QKeySequence("S"), self, activated=self._open_settings)
        QShortcut(QKeySequence("["), self, activated=lambda: self._nudge_conf(-step))
        QShortcut(QKeySequence("]"), self, activated=lambda: self._nudge_conf(+step))
        QShortcut(QKeySequence(","), self, activated=lambda: self._nudge_max(-1))
        QShortcut(QKeySequence("."), self, activated=lambda: self._nudge_max(+1))
        QShortcut(QKeySequence("R"), self, activated=self._toggle_record)
        QShortcut(QKeySequence("C"), self, activated=self._snapshot)
        QShortcut(QKeySequence("O"), self, activated=self.drakevox_generate_now)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        if pipeline.s.spectrum_enabled:
            self.spectrum.start()
        self._paint_spectrum_strip()

        QTimer.singleShot(0, self._force_fullscreen)

    def set_spectrum_enabled(self, enabled: bool) -> None:
        self.pipeline.s.spectrum_enabled = bool(enabled)
        self.pipeline.s.save_persisted()
        if enabled:
            if not self.spectrum.active:
                self.spectrum.start()
        else:
            self.spectrum.stop()
        # Keep strip geometry stable; only mic capture toggles.
        self._paint_spectrum_strip()
        # Re-assert fullscreen in case the WM reacted to layout churn
        QTimer.singleShot(0, self._force_fullscreen)

    def cycle_spectrum_style(self) -> None:
        """Settings: cycle strip look; persist; default style is Phosphor."""
        cur = self.pipeline.s.spectrum_style
        nxt = next_spectrum_style(cur)
        self.pipeline.s.spectrum_style = nxt
        self.pipeline.s.save_persisted()
        self.session._set_flash(
            f"spectrum: {spectrum_style_label(nxt)}", seconds=2.0
        )
        self._paint_spectrum_strip()
        if self._settings_open():
            self._settings_dlg._refresh()

    def set_drakevox_enabled(self, enabled: bool) -> None:
        """ON = show panel + word generation; OFF = hide panel + stop generation."""
        self.pipeline.s.drakevox_enabled = bool(enabled)
        self.pipeline.s.save_persisted()
        self.drakevox.enabled = bool(enabled)
        if self._settings_open():
            self._settings_dlg._refresh()

    def set_drakevox_on_autosnap(self, enabled: bool) -> None:
        """When ON, auto-snap on detect also generates DrakeVox into the JPEG."""
        self.pipeline.s.drakevox_on_autosnap = bool(enabled)
        self.pipeline.s.save_persisted()
        if self._settings_open():
            self._settings_dlg._refresh()

    def nudge_display_brightness(self, delta: int) -> None:
        """Adjust panel/software brightness; persist if change succeeded."""
        info = nudge_brightness(int(delta))
        if info.available and info.percent is not None and info.writable:
            self.pipeline.s.display_brightness = int(info.percent)
            self.pipeline.s.save_persisted()
        if self._settings_open():
            self._settings_dlg._refresh()

    def format_removable_media(self) -> None:
        """Settings: two-tap confirm → format mounted USB/SD for field captures (#8).

        Flow:
          1. **Format removable media…** (only when a stick/card is mounted)
          2. Confirm 1 — warning with label / device / size (Cancel default)
          3. Confirm 2 — final “Erase and format” (Cancel default; no typing)
          4. mkfs needs admin (pkexec / passwordless sudo / root)

        Does not require typing the device name (field-friendly).
        """
        if self.session.recording:
            self.session._set_flash("stop REC before format", seconds=3.0)
            return
        cands = [(v, ok, why) for v, ok, why in list_format_candidates() if ok]
        if not cands:
            self.session._set_flash(
                "no formattable USB/SD (need mounted removable with /dev node)",
                seconds=4.0,
            )
            return
        vol, _ok, _why = cands[0]
        dev = vol.source or "?"
        size_g = 0.0
        try:
            size_g = device_size_bytes(dev) / (1024**3)
        except Exception:
            pass
        kind_name = {
            "sd": "SD card",
            "usb": "USB stick",
            "removable": "removable media",
        }.get(vol.kind, "removable media")
        detail = (
            f"  {kind_name}: {vol.label}\n"
            f"  Device: {dev}\n"
            f"  Mount:  {vol.path}\n"
            f"  Size:   ~{size_g:.1f} GiB"
        )
        # Confirm 1 — cancel is default
        box = QMessageBox(self)
        box.setWindowTitle("Format removable media")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            f"Format this {kind_name} for SLS captures?\n\n"
            f"This will ERASE ALL DATA on:\n\n"
            f"{detail}\n\n"
            f"After format: FAT32 «{DEFAULT_LABEL}» + folder sls-captures/.\n"
            f"Needs admin rights (password prompt or tablet sudoers)."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        yes = box.button(QMessageBox.StandardButton.Yes)
        if yes is not None:
            yes.setText("Continue…")
        box.setStyleSheet(_STYLE)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        # Confirm 2 — still Cancel default; no keyboard typing
        box2 = QMessageBox(self)
        box2.setWindowTitle("Confirm erase")
        box2.setIcon(QMessageBox.Icon.Warning)
        box2.setText(
            f"Last chance — erase and format?\n\n"
            f"{detail}\n\n"
            f"This cannot be undone."
        )
        box2.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        box2.setDefaultButton(QMessageBox.StandardButton.Cancel)
        yes2 = box2.button(QMessageBox.StandardButton.Yes)
        if yes2 is not None:
            yes2.setText("Erase and format")
        box2.setStyleSheet(_STYLE)
        box2.setWindowFlags(box2.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        if box2.exec() != QMessageBox.StandardButton.Yes:
            self.session._set_flash("format cancelled", seconds=2.0)
            return
        self.session._set_flash(f"formatting {dev}…", seconds=2.0)
        QApplication.processEvents()
        res = format_volume_fat32(vol, label=DEFAULT_LABEL)
        self.session._set_flash(res.message, seconds=6.0)
        if res.ok:
            if self.pipeline.s.captures_target != "auto":
                self.pipeline.s.captures_target = "auto"
                self.pipeline.s.save_persisted()
            self.session.set_captures_target("auto")
            self.session.refresh_captures_dir()
        if self._settings_open():
            self._settings_dlg._refresh()

    def apply_field_defaults(self) -> None:
        """Settings Defaults: pose, captures Auto, spectrum style Phosphor."""
        self.pipeline.reset_pose_defaults()
        if not self.session.recording:
            label = self.session.set_captures_target("auto")
            style = spectrum_style_label(self.pipeline.s.spectrum_style)
            self.session._set_flash(
                f"defaults · Captures → {label} · spectrum:{style}"
            )
        else:
            # Persist auto for next session; keep current path while REC
            self.pipeline.s.captures_target = "auto"
            self.pipeline.s.save_persisted()
            self.session._set_flash(
                "defaults saved (captures path after REC stops; spectrum → Phosphor)"
            )
        self._paint_spectrum_strip()
        if self._settings_open():
            self._settings_dlg._refresh()

    def toggle_captures_target(self) -> None:
        """Cycle Local ↔ Auto (USB/SD when mounted). Default is Auto."""
        if self.session.recording:
            self.session._set_flash("stop recording before changing captures path")
            return
        cur = (self.pipeline.s.captures_target or "auto").lower()
        nxt = "local" if cur == "auto" else "auto"
        self.pipeline.s.captures_target = nxt
        self.pipeline.s.save_persisted()
        label = self.session.set_captures_target(nxt)
        self.session._set_flash(f"Captures → {label}")
        if self._settings_open():
            self._settings_dlg._refresh()

    def copy_local_to_media(self) -> None:
        """Copy viewer/captures → mounted media/sls-captures (confirm first)."""
        if self.session.recording:
            self.session._set_flash("stop recording before copy to media")
            return
        if not self.session.has_removable_media():
            self.session._set_flash("no USB/SD media mounted")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Copy local → media")
        box.setText(
            "Copy files from local viewer/captures/\n"
            "onto the mounted USB/SD (sls-captures/)?\n\n"
            "Local files are kept. Existing same-name files on media are skipped."
        )
        box.setIcon(QMessageBox.Icon.Question)
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        yes = box.button(QMessageBox.StandardButton.Yes)
        if yes is not None:
            yes.setText("Copy")
        box.setStyleSheet(_STYLE)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.session.copy_local_captures_to_media()

    def _on_drakevox_word(self, word: str) -> None:
        """Log, speak (TTS), and inject PCM into any active recording."""
        if not word:
            return
        self.session.note_drakevox(word)
        # speak() also calls inject_tts via set_record_callback while REC
        self.tts.speak(word)
        if self._settings_open():
            self._settings_dlg._refresh()

    def drakevox_generate_now(self) -> None:
        """Manual word (key O / Settings). Does nothing while DrakeVox is OFF."""
        if not self.pipeline.s.drakevox_enabled:
            self.session._set_flash("DrakeVox is OFF", seconds=2.0)
            return
        word = self.drakevox.generate_now()
        if word:
            self._on_drakevox_word(word)

    def _paint_spectrum_strip(self) -> None:
        """Always paint into the reserved strip (bars, retry, or idle)."""
        w = max(64, self.spectrum_label.width() or self.width() or 640)
        h = int(self.pipeline.s.spectrum_height)
        if self.pipeline.s.spectrum_enabled:
            # paint_bgr shows bars when live, or "mic retry…" while reconnecting
            strip = self.spectrum.paint_bgr(
                w, h, style=self.pipeline.s.spectrum_style
            )
        else:
            strip = np.zeros((h, w, 3), dtype=np.uint8)
            strip[:] = (12, 12, 12)
            cv2.putText(
                strip,
                "spectrum off",
                (8, max(14, h // 2 + 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (70, 70, 70),
                1,
                cv2.LINE_AA,
            )
        self.spectrum_label.setPixmap(bgr_to_qpixmap(strip))

    def _settings_open(self) -> bool:
        return self._settings_dlg is not None and self._settings_dlg.isVisible()

    def _open_settings(self) -> None:
        if self._settings_dlg is None:
            self._settings_dlg = SettingsDialog(
                self.pipeline,
                self.spectrum,
                self.session,
                self.drakevox,
                self,
            )
        if self._settings_dlg.isVisible():
            self._settings_dlg.raise_()
            self._settings_dlg.activateWindow()
            return
        self._settings_dlg._refresh()
        self._settings_dlg.show()
        self._settings_dlg.raise_()

    def _on_escape(self) -> None:
        if self._settings_open():
            self._settings_dlg.reject()
            return
        self._request_quit()

    def _request_quit(self) -> None:
        """Quit button / Q / Esc (when Settings closed) — confirm first.

        When firmware sets SLS_QUIT_ACTION=shutdown, dialog is “Power off?”
        and exit code 10 (firmware launcher does host poweroff).
        """
        if self._quit_confirmed:
            self.close()
            return
        power_off = bool(self.pipeline.s.quit_powers_off)
        box = QMessageBox(self)
        if power_off:
            box.setWindowTitle("Power off")
            box.setText("Power off this tablet?")
            if self.session.recording:
                box.setInformativeText(
                    "Recording will be stopped and saved, then the system powers off."
                )
            else:
                box.setInformativeText(
                    "Camera and mic will stop, then the system powers off."
                )
        else:
            box.setWindowTitle("Quit SLS Camera")
            box.setText("Quit SLS Camera?")
            if self.session.recording:
                box.setInformativeText("Recording will be stopped and saved.")
            else:
                box.setInformativeText("Camera and mic capture will stop.")
        box.setIcon(QMessageBox.Icon.Question)
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        yes = box.button(QMessageBox.StandardButton.Yes)
        if yes is not None:
            yes.setText("Power off" if power_off else "Quit")
        box.setStyleSheet(_STYLE)
        # Keep dialog above fullscreen field UI
        box.setWindowFlags(
            box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        if box.exec() == QMessageBox.StandardButton.Yes:
            self._quit_confirmed = True
            self.close()

    def _nudge_conf(self, delta: float) -> None:
        self.pipeline.adjust_pose_confidence(delta)
        if self._settings_open():
            self._settings_dlg._refresh()

    def _nudge_max(self, delta: int) -> None:
        self.pipeline.adjust_max_poses(delta)
        if self._settings_open():
            self._settings_dlg._refresh()

    def _toggle_mirror(self) -> None:
        self.pipeline.mirror = not self.pipeline.mirror
        if self._settings_open():
            self._settings_dlg._refresh()

    def _restore_led_after_snap(self) -> None:
        """After snap LED cue: red if recording, else idle green/off."""
        self.pipeline.set_recording_led(self.session.recording)

    def _compose_drakevox(self, frame) -> "np.ndarray":
        """Copy frame and paint DrakeVox overlay when enabled."""
        display = frame.copy()
        s = self.pipeline.s
        if s.drakevox_enabled:
            paint_drakevox_bgr(
                display,
                enabled=True,
                flash=self.drakevox.flash_active(),
                history=self.drakevox.history()[:5],
                pip_w=s.ir_pip_width,
                pip_h=s.ir_pip_height,
                pip_margin=s.ir_pip_margin,
                pip_corner=s.ir_pip_corner,
                history_n=5,
            )
        return display

    def _snapshot(self, *, fire_drakevox: bool = False) -> None:
        """Snap JPEG. Optionally fire DrakeVox (auto-snap path) so the word is in the photo."""
        frame = self.pipeline.get_bgr()
        if frame is None or getattr(frame, "size", 0) == 0:
            self.session.snapshot(frame)  # flash error
            return

        # Auto-snap only (when setting on): generate word + TTS like key O
        if (
            fire_drakevox
            and self.pipeline.s.drakevox_enabled
            and self.pipeline.s.drakevox_on_autosnap
        ):
            word = self.drakevox.generate_now()
            if word:
                self._on_drakevox_word(word)

        # Composite may include current DrakeVox panel (no forced word on manual Snap)
        display = self._compose_drakevox(frame)
        path = self.session.snapshot(display)
        if path is not None:
            # LED: red flash, then restore (green idle / red if still REC)
            self.pipeline.set_led(freenect_io.LED_RED)
            QTimer.singleShot(400, self._restore_led_after_snap)
        if self._settings_open():
            self._settings_dlg._refresh()

    def _toggle_record(self) -> None:
        if self.session.recording:
            self.session.stop_record()
            self.pipeline.set_recording_led(False)
        else:
            frame = self.pipeline.get_bgr()
            # Share spectrum mic stream when present (one open of Kinect USB Audio).
            path = self.session.start_record(
                frame,
                fps=self.pipeline.s.record_fps,
                spectrum=self.spectrum,
            )
            if path is not None:
                self.pipeline.set_recording_led(True)
        self._refresh_record_button()
        if self._settings_open():
            self._settings_dlg._refresh()

    def clear_captures(self) -> None:
        """Settings: delete captures/ after confirm (blocked while recording)."""
        if self.session.recording:
            self.session._set_flash("stop recording before clearing captures")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Clear captures")
        dest = self.session.captures_dir
        box.setText(
            f"Delete all files in:\n{dest}\n\n"
            "(snapshots, recordings, session logs)?\n\n"
            "This cannot be undone."
        )
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        yes = box.button(QMessageBox.StandardButton.Yes)
        if yes is not None:
            yes.setText("Delete")
        box.setStyleSheet(_STYLE)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.session.clear_captures()

    def _refresh_record_button(self) -> None:
        if self.session.recording:
            self.btn_record.setText(f"Stop {self.session.recording_elapsed_str()}")
        else:
            self.btn_record.setText("Record")

    def _force_fullscreen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            self.setMinimumSize(geo.size())
            self.setGeometry(geo)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._force_fullscreen()

    def _tick(self) -> None:
        # Infinite mic retry when spectrum on (or recorder is piggybacking)
        if self.pipeline.s.spectrum_enabled or self.session.recording:
            self.spectrum.ensure_running()

        # DrakeVox 5–15 min timer + TTS
        if self.pipeline.s.drakevox_enabled:
            fired = self.drakevox.tick()
            if fired:
                self._on_drakevox_word(fired)

        mx = self.pipeline.max_poses
        flash = self.session.flash_message()
        if self.session.recording:
            rec = f" · REC {self.session.recording_elapsed_str()}"
            self._refresh_record_button()
        else:
            rec = ""
            if self.btn_record.text() != "Record":
                self.btn_record.setText("Record")
        dv = ""
        if self.pipeline.s.drakevox_enabled and self.drakevox.current:
            dv = f" · DRAKEVOX:{self.drakevox.current}"
        bat = self.battery.status_token()
        bat_s = f" · {bat}" if bat else ""
        # Refresh auto media path occasionally (plug pen drive / SD mid-session)
        self._media_poll_i = getattr(self, "_media_poll_i", 0) + 1
        if self._media_poll_i % 90 == 0:  # ~3s at 33ms tick
            self.session.refresh_captures_dir()
        # Re-assert xset DPMS-off periodically (some WMs re-enable blanking)
        self._inhibit_refresh_i = getattr(self, "_inhibit_refresh_i", 0) + 1
        if self.display_inhibit.active and self._inhibit_refresh_i % 1800 == 0:
            self.display_inhibit.refresh_x11()
        cap = self.session.captures_label
        cap_s = f" · CAP:{cap}" if cap else ""
        base = (
            f"{self.pipeline.status}  ·  "
            f"Detected:{self.pipeline.poses_count}/{mx}{rec}{dv}{bat_s}{cap_s}"
        )
        self.status.setText(f"{flash}  ·  {base}" if flash else base)

        frame = self.pipeline.get_bgr()
        if frame is not None:
            # Detect appear → optional auto-snap (+ optional DrakeVox via setting)
            det = self.session.note_detection(self.pipeline.poses_count)
            if det == "appear" and self.pipeline.s.auto_snap_on_detect:
                self._snapshot(fire_drakevox=True)

            # Composite DrakeVox overlay (hidden when OFF), then record + display
            display = self._compose_drakevox(frame)
            if self.session.recording:
                self.session.write_frame(display)
            pix = bgr_to_qpixmap(display)
            target = self.video.size()
            if target.width() >= 2 and target.height() >= 2:
                scaled = pix.scaled(
                    target,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.video.setPixmap(scaled)

        self._paint_spectrum_strip()

    def closeEvent(self, event) -> None:
        if not self._quit_confirmed:
            event.ignore()
            self._request_quit()
            return
        self._timer.stop()
        if self.session.recording:
            self.session.stop_record()
            self.pipeline.set_recording_led(False)
        self.spectrum.stop()
        self.display_inhibit.stop()
        if self._settings_dlg is not None:
            self._settings_dlg.close()
        # Clean teardown; exit 10 only signals firmware launcher (never poweroff here).
        power_off = bool(self.pipeline.s.quit_powers_off)
        self._app_exit_code = EXIT_POWEROFF if power_off else EXIT_OK
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.exit(int(self._app_exit_code))


def run_qt(pipeline: FramePipeline) -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SLS Camera")
    # Primary-screen geometry for hardware matrix / tablet bring-up (#6)
    geom_line = log_display_geometry(app)
    win = SlsMainWindow(pipeline)
    win._app_exit_code = EXIT_OK
    win._display_geometry_line = geom_line
    win.showFullScreen()
    # Re-log after fullscreen in case WM/screen metrics settle
    def _relog_geometry() -> None:
        line = log_display_geometry(app)
        win._display_geometry_line = line
        # Brief status flash so operators/techs see it on first tablet boot
        if hasattr(win, "session") and win.session is not None:
            win.session._set_flash(line, seconds=4.0)

    QTimer.singleShot(250, _relog_geometry)
    code = app.exec()
    # Prefer window exit intent (10 = power off) over default Qt 0
    out = int(getattr(win, "_app_exit_code", code) or 0)
    if out == 0 and int(code) != 0:
        out = int(code)
    return out
