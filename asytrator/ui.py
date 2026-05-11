"""PyQt6 main window.

Pure presentation: buttons, fields, status label. All logic lives in
AppController; the UI just calls methods on it and listens for signals.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QGroupBox,
)


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("AsyTrator")
        self.setMinimumWidth(480)

        self._build_ui()
        self._wire_signals()

    def _build_ui(self):
        # 1. Status label at the top — single source of truth for "what's happening".
        self.status_label = QLabel("Starting...")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "padding: 10px; background: #222; color: #eee; border-radius: 6px;"
        )

        # 2. Record button — toggles between start / stop.
        self.record_btn = QPushButton("● Start Recording")
        self.record_btn.setMinimumHeight(40)
        self.record_btn.clicked.connect(self.controller.toggle_recording)

        # 3. Dubbing section — language inputs + button.
        dub_box = QGroupBox("Dubbing")
        dub_layout = QVBoxLayout()

        lang_row = QHBoxLayout()
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("source (e.g. de)")
        self.source_input.setMaxLength(2)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("target (e.g. en)")
        self.target_input.setMaxLength(2)
        lang_row.addWidget(QLabel("From:"))
        lang_row.addWidget(self.source_input)
        lang_row.addWidget(QLabel("To:"))
        lang_row.addWidget(self.target_input)
        dub_layout.addLayout(lang_row)

        self.dub_btn = QPushButton("Start Dubbing")
        self.dub_btn.setEnabled(False)
        self.dub_btn.clicked.connect(self._on_dub_clicked)
        dub_layout.addWidget(self.dub_btn)
        dub_box.setLayout(dub_layout)

        # 4. Play button — sends the dubbed video to the virtual cam.
        self.play_btn = QPushButton("▶ Play Dubbed Video")
        self.play_btn.setMinimumHeight(40)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.controller.start_playback)

        # Assemble.
        root = QVBoxLayout()
        root.addWidget(self.status_label)
        root.addWidget(self.record_btn)
        root.addWidget(dub_box)
        root.addWidget(self.play_btn)
        root.addStretch()

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

    def _wire_signals(self):
        c = self.controller
        c.status_message.connect(self._set_status)
        c.recording_changed.connect(self._on_recording_changed)
        c.recording_ready.connect(self.dub_btn.setEnabled)
        c.dubbing_ready.connect(self.play_btn.setEnabled)
        c.dubbing_in_progress.connect(lambda busy: self.dub_btn.setEnabled(not busy))

    # --- Slots ---

    def _set_status(self, msg):
        self.status_label.setText(msg)

    def _on_recording_changed(self, recording):
        self.record_btn.setText("■ Stop Recording" if recording else "● Start Recording")

    def _on_dub_clicked(self):
        source = self.source_input.text().strip().lower()
        target = self.target_input.text().strip().lower()
        if not source or not target:
            self._set_status("Enter both source and target language codes (e.g. de, en).")
            return
        self.controller.start_dubbing(source, target)

    def closeEvent(self, event):
        self.controller.stop()
        event.accept()
