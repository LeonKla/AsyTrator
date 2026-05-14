"""Video preview dialog — plays back a list of RGB numpy frames in a window."""
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider,
)

from asytrator.config import FPS


class PreviewDialog(QDialog):
    def __init__(self, frames: list, title: str, parent=None):
        super().__init__(parent)
        self.frames = frames
        self.index = 0
        self.playing = True

        self.setWindowTitle(title)
        self.setMinimumSize(640, 420)

        # Video display
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background: black;")
        self.video_label.setMinimumSize(640, 360)

        # Seek slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max(len(frames) - 1, 0))
        self.slider.sliderMoved.connect(self._on_seek)

        # Controls row
        self.play_btn = QPushButton("⏸ Pause")
        self.play_btn.setFixedWidth(90)
        self.play_btn.clicked.connect(self._toggle_play)

        self.time_label = QLabel()
        self.time_label.setFixedWidth(100)

        controls = QHBoxLayout()
        controls.addWidget(self.play_btn)
        controls.addWidget(self.slider)
        controls.addWidget(self.time_label)

        layout = QVBoxLayout()
        layout.addWidget(self.video_label)
        layout.addLayout(controls)
        self.setLayout(layout)

        # Playback timer
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / FPS))
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self._show_frame(0)

    def _tick(self):
        if not self.playing:
            return
        next_index = self.index + 1
        if next_index >= len(self.frames):
            self.playing = False
            self.play_btn.setText("▶ Play")
            return
        self._show_frame(next_index)

    def _show_frame(self, index: int):
        self.index = index
        frame = self.frames[index]  # RGB numpy (H, W, 3)
        h, w, ch = frame.shape
        qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.video_label.width(),
            self.video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.video_label.setPixmap(pixmap)
        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)
        self._update_time()

    def _update_time(self):
        def fmt(s): return f"{int(s)//60:02d}:{int(s)%60:02d}"
        current = self.index / FPS
        total = len(self.frames) / FPS
        self.time_label.setText(f"{fmt(current)} / {fmt(total)}")

    def _toggle_play(self):
        if self.playing:
            self.playing = False
            self.play_btn.setText("▶ Play")
        else:
            if self.index >= len(self.frames) - 1:
                self.index = 0
            self.playing = True
            self.play_btn.setText("⏸ Pause")

    def _on_seek(self, value: int):
        self.playing = False
        self.play_btn.setText("▶ Play")
        self._show_frame(value)

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()
