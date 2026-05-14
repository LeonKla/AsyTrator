"""The brain of the app.

Owns every component (capture, audio, virtual cam, dubbing) and coordinates
their state. Exposes Qt signals so the UI can react without polling — when
recording stops, when dubbing finishes, etc.

Why a QObject: signals/slots are Qt's thread-safe way to push events from
worker threads back to the UI thread. Worker thread emits -> Qt queues it ->
UI thread handles it. No manual locking needed for UI updates.
"""
import os
from PyQt6.QtCore import QObject, pyqtSignal

from asytrator import config
from asytrator.capture.video import VideoCapture
from asytrator.capture.audio import AudioCapture
from asytrator.virtual_cam import VirtualCamOutput
from asytrator.dubbing.manager import DubbingManager
from asytrator.media_io import save_video_frames, save_audio, merge_audio_video


class AppController(QObject):
    # Signals — the UI connects to these.
    status_message = pyqtSignal(str)
    recording_changed = pyqtSignal(bool)     # True = currently recording
    recording_ready = pyqtSignal(bool)       # True = a saved recording exists
    dubbing_ready = pyqtSignal(bool)         # True = dubbed video loaded
    dubbing_in_progress = pyqtSignal(bool)
    playback_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        os.makedirs(config.MEDIA_DIR, exist_ok=True)

        self.video = VideoCapture()
        self.audio = AudioCapture()
        self.vcam = VirtualCamOutput(self.video)
        self.dubbing = DubbingManager()

        self._has_recording = False
        self._has_dubbing = False
        self._dubbing_running = False
        self._recorded_frames = []
        self._dubbed_frames = []

    def start(self):
        self.video.start()
        self.audio.start_stream()
        self.vcam.start()
        self.status_message.emit("Ready. Click 'Start Recording' to begin.")

    def stop(self):
        self.vcam.stop()
        self.audio.stop_stream()
        self.video.stop()

    # --- Recording ---

    def toggle_recording(self):
        if self.video.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        # Freeze current buffer as the cover loop so viewers don't see the
        # camera while we're recording the real take behind it.
        cover = self.video.snapshot_buffer()
        self.vcam.set_loop(cover)
        self.video.begin_recording()
        self.audio.begin_recording()

        # Recording invalidates any prior recording/dubbing.
        self._has_recording = False
        self._has_dubbing = False
        self._recorded_frames = []
        self._dubbed_frames = []
        self.recording_ready.emit(False)
        self.dubbing_ready.emit(False)
        self.recording_changed.emit(True)
        self.status_message.emit("Recording — cover loop showing in virtual cam.")

    def _stop_recording(self):
        frames = self.video.end_recording()
        chunks = self.audio.end_recording()
        self.vcam.set_live()
        self.recording_changed.emit(False)
        self.status_message.emit(
            f"Recording stopped ({len(frames) // config.FPS}s). Saving & merging..."
        )

        # Save synchronously — frames/chunks are already captured, this is just
        # disk + ffmpeg. Could move to a thread later if it feels slow.
        self._recorded_frames = frames
        save_video_frames(frames, config.RECORD_VIDEO)
        if chunks:
            save_audio(chunks, config.RECORD_AUDIO)
            merge_audio_video(config.RECORD_VIDEO, config.RECORD_AUDIO, config.RECORD_OUTPUT)
            self._has_recording = True
            self.recording_ready.emit(True)
            self.status_message.emit("Recording saved. Ready to dub.")
        else:
            self.status_message.emit(
                "WARNING: No audio captured — check microphone device index."
            )

    # --- Dubbing ---

    def start_dubbing(self, source_lang, target_lang, provider="elevenlabs"):
        if not self._has_recording:
            self.status_message.emit("Nothing recorded yet.")
            return
        if self._dubbing_running:
            return
        self._dubbing_running = True
        self._has_dubbing = False
        self.dubbing_in_progress.emit(True)
        self.dubbing_ready.emit(False)
        provider_label = "HeyGen" if provider == "heygen" else "ElevenLabs"
        self.status_message.emit(
            f"Dubbing via {provider_label} ({source_lang} → {target_lang}), this may take a few minutes..."
        )
        self.dubbing.run_async(
            config.RECORD_OUTPUT, source_lang, target_lang, provider,
            on_success=self._on_dubbing_success,
            on_error=self._on_dubbing_error,
        )

    def _on_dubbing_success(self, frames):
        # Called from worker thread — signals cross threads safely.
        self._dubbing_running = False
        self._has_dubbing = True
        self._dubbed_frames = frames
        self.dubbing_in_progress.emit(False)
        self.dubbing_ready.emit(True)
        self.status_message.emit("Dubbing complete. Press 'Play' to send to virtual cam.")

    def _on_dubbing_error(self, err):
        self._dubbing_running = False
        self.dubbing_in_progress.emit(False)
        self.status_message.emit(f"Dubbing failed: {err}")

    # --- Playback ---

    def start_playback(self):
        if not self._has_dubbing:
            self.status_message.emit("No dubbed video yet.")
            return
        self.vcam.set_playback(self._dubbed_frames, on_done=self.playback_finished.emit)
        self.status_message.emit("Playing dubbed video in virtual cam...")
