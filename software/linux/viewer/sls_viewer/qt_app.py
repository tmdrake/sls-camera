"""Native Qt fullscreen always-on-top SLS window."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .pipeline import FramePipeline


def bgr_to_qpixmap(bgr: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


class SlsMainWindow(QMainWindow):
    """Fullscreen, always-on-top field UI."""

    def __init__(self, pipeline: FramePipeline):
        super().__init__()
        self.pipeline = pipeline
        self.setWindowTitle("SLS Camera")
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background-color: #000000; color: #c8c8c8; }
            QLabel#video { background-color: #000000; }
            QLabel#status {
                color: #aaaaaa; font-size: 14px; padding: 4px 8px;
            }
            QLabel#title {
                color: #00ffb4; font-size: 16px; font-weight: 700;
                letter-spacing: 2px; padding: 4px 8px;
            }
            QPushButton {
                min-height: 48px; min-width: 110px;
                background-color: rgba(0, 40, 30, 220);
                color: #00ffb4; border: 1px solid #00ffb4;
                border-radius: 8px; font-size: 15px; font-weight: 600;
                padding: 8px 14px;
            }
            QPushButton:pressed { background-color: rgba(0, 80, 60, 240); }
            """
        )

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

        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 8, 12, 12)
        bar_layout.setSpacing(8)

        self.title = QLabel("SLS CAMERA")
        self.title.setObjectName("title")
        self.status = QLabel("starting…")
        self.status.setObjectName("status")

        self.btn_mirror = QPushButton(
            "Mirror: ON" if pipeline.mirror else "Mirror: OFF"
        )
        self.btn_mirror.clicked.connect(self._toggle_mirror)
        self.btn_quit = QPushButton("Quit")
        self.btn_quit.clicked.connect(self.close)

        bar_layout.addWidget(self.title)
        bar_layout.addWidget(self.status, stretch=1)
        bar_layout.addWidget(self.btn_mirror)
        bar_layout.addWidget(self.btn_quit)
        layout.addWidget(bar)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        QShortcut(QKeySequence("Q"), self, activated=self.close)
        QShortcut(QKeySequence("F"), self, activated=self._force_fullscreen)
        QShortcut(QKeySequence("M"), self, activated=self._toggle_mirror)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        QTimer.singleShot(0, self._force_fullscreen)

    def _force_fullscreen(self) -> None:
        self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._force_fullscreen()

    def _toggle_mirror(self) -> None:
        self.pipeline.mirror = not self.pipeline.mirror
        self.btn_mirror.setText(
            "Mirror: ON" if self.pipeline.mirror else "Mirror: OFF"
        )

    def _tick(self) -> None:
        self.status.setText(
            f"{self.pipeline.status}  ·  {self.pipeline.fps:.1f} fps  ·  "
            f"Detected:{self.pipeline.poses_count}"
        )
        self.btn_mirror.setText(
            "Mirror: ON" if self.pipeline.mirror else "Mirror: OFF"
        )
        frame = self.pipeline.get_bgr()
        if frame is None:
            return
        pix = bgr_to_qpixmap(frame)
        target = self.video.size()
        if target.width() < 2 or target.height() < 2:
            return
        scaled = pix.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.video.setPixmap(scaled)

    def closeEvent(self, event) -> None:
        self._timer.stop()
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
