"""PyQt6 main window.

Pure presentation: buttons, fields, status label. All logic lives in
AppController; the UI just calls methods on it and listens for signals.
"""
import sounddevice as sd
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QGroupBox, QComboBox,
)
from asytrator import config
from asytrator.preview import PreviewDialog


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

        # 2b. Restore button — loads any media left on disk from a prior session.
        self.restore_btn = QPushButton("↩ Load Previous Session")
        self.restore_btn.clicked.connect(self.controller.load_previous_session)

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

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("ElevenLabs (faster, no lip-sync)", "elevenlabs")
        self.provider_combo.addItem("HeyGen (slower, with lip-sync)", "heygen")
        provider_row.addWidget(self.provider_combo)
        dub_layout.addLayout(provider_row)

        self.dub_btn = QPushButton("Start Dubbing")
        self.dub_btn.setEnabled(False)
        self.dub_btn.clicked.connect(self._on_dub_clicked)
        dub_layout.addWidget(self.dub_btn)
        dub_box.setLayout(dub_layout)

        # 4. Preview + broadcast row for recording
        self.preview_rec_btn = QPushButton("Preview Recording")
        self.preview_rec_btn.setEnabled(False)
        self.preview_rec_btn.clicked.connect(self._on_preview_recording)

        # 5. Audio output device selector.
        audio_out_box = QGroupBox("Audio Output (for Teams microphone)")
        audio_out_layout = QHBoxLayout()
        audio_out_layout.addWidget(QLabel("Device:"))
        self.audio_out_combo = QComboBox()
        self._populate_audio_output_devices()
        self.audio_out_combo.currentIndexChanged.connect(self._on_audio_out_changed)
        audio_out_layout.addWidget(self.audio_out_combo)
        audio_out_box.setLayout(audio_out_layout)

        # 6. Preview + broadcast row for dubbed video
        preview_dub_row = QHBoxLayout()
        self.preview_dub_btn = QPushButton("Preview Dubbed")
        self.preview_dub_btn.setEnabled(False)
        self.preview_dub_btn.clicked.connect(self._on_preview_dubbed)
        self.play_btn = QPushButton("▶ Broadcast Dubbed")
        self.play_btn.setMinimumHeight(36)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.controller.start_playback)
        preview_dub_row.addWidget(self.preview_dub_btn)
        preview_dub_row.addWidget(self.play_btn)

        # Assemble.
        root = QVBoxLayout()
        root.addWidget(self.status_label)
        root.addWidget(self.restore_btn)
        root.addWidget(self.record_btn)
        root.addWidget(self.preview_rec_btn)
        root.addWidget(dub_box)
        root.addWidget(audio_out_box)
        root.addLayout(preview_dub_row)
        root.addStretch()

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

    def _wire_signals(self):
        c = self.controller
        c.status_message.connect(self._set_status)
        c.recording_changed.connect(self._on_recording_changed)
        c.recording_ready.connect(self.dub_btn.setEnabled)
        c.recording_ready.connect(self.preview_rec_btn.setEnabled)
        c.dubbing_ready.connect(self.play_btn.setEnabled)
        c.dubbing_ready.connect(self.preview_dub_btn.setEnabled)
        c.dubbing_in_progress.connect(lambda busy: self.dub_btn.setEnabled(not busy))
        c.session_loading.connect(lambda loading: self.restore_btn.setEnabled(not loading))
        c.session_loading.connect(lambda loading: self.restore_btn.setText(
            "↩ Loading…" if loading else "↩ Load Previous Session"
        ))

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
        provider = self.provider_combo.currentData()
        self.controller.start_dubbing(source, target, provider)

    def _on_preview_recording(self):
        frames = self.controller._recorded_frames
        if frames:
            PreviewDialog(frames, "Preview — Recording", parent=self).exec()

    def _on_preview_dubbed(self):
        frames = self.controller._dubbed_frames
        if frames:
            PreviewDialog(frames, "Preview — Dubbed Video", parent=self).exec()

    def _populate_audio_output_devices(self):
        """Fill the combo with output-capable devices, pre-selecting the configured one."""
        self.audio_out_combo.blockSignals(True)
        self.audio_out_combo.clear()
        self.audio_out_combo.addItem("System Default", None)
        configured = (config.AUDIO_OUTPUT_DEVICE or "").lower()
        best_match = 0
        try:
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_output_channels"] > 0:
                    label = f"{dev['name']} [{i}]"
                    self.audio_out_combo.addItem(label, i)
                    if configured and configured in dev["name"].lower():
                        best_match = self.audio_out_combo.count() - 1
        except Exception:
            pass
        self.audio_out_combo.setCurrentIndex(best_match)
        self.audio_out_combo.blockSignals(False)

    def _on_audio_out_changed(self, index):
        device_index = self.audio_out_combo.itemData(index)
        config.AUDIO_OUTPUT_DEVICE = device_index
        self.controller.audio_out._device = device_index
        # Hot-swap the live passthrough to the newly selected device.
        self.controller.passthrough.update_output_device(device_index)

    def closeEvent(self, event):
        self.controller.stop()
        event.accept()
