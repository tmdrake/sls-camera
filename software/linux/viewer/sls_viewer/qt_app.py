"""Native Qt fullscreen always-on-top SLS window."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .session_io import SessionRecorder
from .spectrum import SpectrumAnalyzer

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
"""


def bgr_to_qpixmap(bgr: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


class SettingsDialog(QDialog):
    """Popup: max people, confidence, mirror, spectrum, session tools."""

    def __init__(
        self,
        pipeline: FramePipeline,
        spectrum: SpectrumAnalyzer,
        session: SessionRecorder,
        parent=None,
    ):
        super().__init__(parent)
        self.pipeline = pipeline
        self.spectrum = spectrum
        self.session = session
        self.setWindowTitle("Settings")
        self.setModal(False)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(_STYLE)
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        hdr = QLabel("SETTINGS")
        hdr.setObjectName("hdr")
        root.addWidget(hdr)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        step = pipeline.s.pose_conf_step
        row = 0

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

        # Mirror
        grid.addWidget(QLabel("Mirror"), row, 0)
        self.btn_mirror = QPushButton()
        self.btn_mirror.setObjectName("wide")
        self.btn_mirror.clicked.connect(self._toggle_mirror)
        grid.addWidget(self.btn_mirror, row, 1, 1, 3)
        row += 1

        # Spectrum
        grid.addWidget(QLabel("Spectrum"), row, 0)
        self.btn_spectrum = QPushButton()
        self.btn_spectrum.setObjectName("wide")
        self.btn_spectrum.clicked.connect(self._toggle_spectrum)
        grid.addWidget(self.btn_spectrum, row, 1, 1, 3)
        row += 1

        # Auto-snap
        grid.addWidget(QLabel("Auto-snap on detect"), row, 0)
        self.btn_autosnap = QPushButton()
        self.btn_autosnap.setObjectName("wide")
        self.btn_autosnap.clicked.connect(self._toggle_autosnap)
        grid.addWidget(self.btn_autosnap, row, 1, 1, 3)
        row += 1

        root.addLayout(grid)

        # Session actions
        act = QHBoxLayout()
        self.btn_snap = QPushButton("Snapshot")
        self.btn_snap.setObjectName("wide")
        self.btn_snap.clicked.connect(self._snapshot)
        self.btn_record = QPushButton("Record")
        self.btn_record.setObjectName("wide")
        self.btn_record.clicked.connect(self._toggle_record)
        act.addWidget(self.btn_snap)
        act.addWidget(self.btn_record)
        act.addStretch(1)
        root.addLayout(act)

        self.mic_label = QLabel("")
        self.mic_label.setStyleSheet("color: #666; font-size: 11px;")
        self.mic_label.setWordWrap(True)
        root.addWidget(self.mic_label)

        hint = QLabel("Keys: [ ] conf  , . max  M mirror  S settings  Esc close")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("wide")
        self.btn_close.clicked.connect(self.accept)
        close_row.addWidget(self.btn_close)
        root.addLayout(close_row)

        self._refresh()

    def _refresh(self) -> None:
        self.max_label.setText(f"{self.pipeline.max_poses}")
        self.conf_label.setText(f"{self.pipeline.pose_confidence:.2f}")
        self.btn_mirror.setText("ON" if self.pipeline.mirror else "OFF")
        self.btn_spectrum.setText(
            "ON" if self.pipeline.s.spectrum_enabled else "OFF"
        )
        self.btn_autosnap.setText(
            "ON" if self.pipeline.s.auto_snap_on_detect else "OFF"
        )
        self.btn_record.setText(
            "Stop rec" if self.session.recording else "Record"
        )
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

    def _toggle_autosnap(self) -> None:
        self.pipeline.s.auto_snap_on_detect = not self.pipeline.s.auto_snap_on_detect
        self.pipeline.s.save_persisted()
        self._refresh()

    def _snapshot(self) -> None:
        frame = self.pipeline.get_bgr()
        self.session.snapshot(frame)
        self._refresh()

    def _toggle_record(self) -> None:
        if self.session.recording:
            self.session.stop_record()
        else:
            frame = self.pipeline.get_bgr()
            self.session.start_record(frame, fps=self.pipeline.s.record_fps)
        self._refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh()
        parent = self.parentWidget()
        if parent is not None:
            pg = parent.geometry()
            self.adjustSize()
            x = pg.x() + pg.width() - self.width() - 24
            y = pg.y() + pg.height() - self.height() - 72
            self.move(max(0, x), max(0, y))


class SlsMainWindow(QMainWindow):
    """Fullscreen, always-on-top field UI."""

    def __init__(self, pipeline: FramePipeline):
        super().__init__()
        self.pipeline = pipeline
        self.spectrum = SpectrumAnalyzer(n_bars=pipeline.s.spectrum_bars)
        self.session = SessionRecorder()
        self._settings_dlg: Optional[SettingsDialog] = None
        self.setWindowTitle("SLS Camera")
        self.setStyleSheet(_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video = QLabel()
        self.video.setObjectName("video")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setScaledContents(False)
        layout.addWidget(self.video, stretch=1)

        self.spectrum_label = QLabel()
        self.spectrum_label.setObjectName("spectrum")
        self.spectrum_label.setFixedHeight(pipeline.s.spectrum_height)
        self.spectrum_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.spectrum_label)

        bar = QWidget()
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
        self.btn_quit = QPushButton("Quit")
        self.btn_quit.setObjectName("wide")
        self.btn_quit.clicked.connect(self.close)

        bar_layout.addWidget(self.title)
        bar_layout.addWidget(self.status, stretch=1)
        bar_layout.addWidget(self.btn_settings)
        bar_layout.addWidget(self.btn_quit)
        layout.addWidget(bar)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        step = pipeline.s.pose_conf_step
        QShortcut(QKeySequence("Escape"), self, activated=self._on_escape)
        QShortcut(QKeySequence("Q"), self, activated=self.close)
        QShortcut(QKeySequence("F"), self, activated=self._force_fullscreen)
        QShortcut(QKeySequence("M"), self, activated=self._toggle_mirror)
        QShortcut(QKeySequence("S"), self, activated=self._open_settings)
        QShortcut(QKeySequence("["), self, activated=lambda: self._nudge_conf(-step))
        QShortcut(QKeySequence("]"), self, activated=lambda: self._nudge_conf(+step))
        QShortcut(QKeySequence(","), self, activated=lambda: self._nudge_max(-1))
        QShortcut(QKeySequence("."), self, activated=lambda: self._nudge_max(+1))

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        if pipeline.s.spectrum_enabled:
            self.spectrum.start()
        self._sync_spectrum_visibility()

        QTimer.singleShot(0, self._force_fullscreen)

    def set_spectrum_enabled(self, enabled: bool) -> None:
        self.pipeline.s.spectrum_enabled = bool(enabled)
        self.pipeline.s.save_persisted()
        if enabled:
            if not self.spectrum.active:
                self.spectrum.start()
        else:
            self.spectrum.stop()
        self._sync_spectrum_visibility()

    def _sync_spectrum_visibility(self) -> None:
        on = bool(self.pipeline.s.spectrum_enabled)
        self.spectrum_label.setVisible(on)
        if on:
            self.spectrum_label.setFixedHeight(self.pipeline.s.spectrum_height)

    def _settings_open(self) -> bool:
        return self._settings_dlg is not None and self._settings_dlg.isVisible()

    def _open_settings(self) -> None:
        if self._settings_dlg is None:
            self._settings_dlg = SettingsDialog(
                self.pipeline, self.spectrum, self.session, self
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

    def _force_fullscreen(self) -> None:
        self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._force_fullscreen()

    def _tick(self) -> None:
        mx = self.pipeline.max_poses
        flash = self.session.flash_message()
        rec = " · REC" if self.session.recording else ""
        base = (
            f"{self.pipeline.status}  ·  {self.pipeline.fps:.1f} fps  ·  "
            f"Detected:{self.pipeline.poses_count}/{mx}{rec}"
        )
        self.status.setText(f"{flash}  ·  {base}" if flash else base)

        frame = self.pipeline.get_bgr()
        if frame is not None:
            if self.session.recording:
                self.session.write_frame(frame)
            self.session.note_detection(
                self.pipeline.poses_count,
                self.pipeline.s.auto_snap_on_detect,
                frame,
            )
            pix = bgr_to_qpixmap(frame)
            target = self.video.size()
            if target.width() >= 2 and target.height() >= 2:
                scaled = pix.scaled(
                    target,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.video.setPixmap(scaled)

        if self.pipeline.s.spectrum_enabled and self.spectrum_label.isVisible():
            w = max(64, self.spectrum_label.width())
            h = self.pipeline.s.spectrum_height
            strip = self.spectrum.paint_bgr(w, h)
            self.spectrum_label.setPixmap(bgr_to_qpixmap(strip))

    def closeEvent(self, event) -> None:
        self._timer.stop()
        if self.session.recording:
            self.session.stop_record()
        self.spectrum.stop()
        if self._settings_dlg is not None:
            self._settings_dlg.close()
        super().closeEvent(event)


def run_qt(pipeline: FramePipeline) -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SLS Camera")
    win = SlsMainWindow(pipeline)
    win.showFullScreen()
    code = app.exec()
    return int(code)
