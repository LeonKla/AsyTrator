"""The brain of the app.

Owns every component (capture, audio, virtual cam, dubbing) and coordinates
their state. Exposes Qt signals so the UI can react without polling — when
recording stops, when dubbing finishes, etc.

Why a QObject: signals/slots are Qt's thread-safe way to push events from
worker threads back to the UI thread. Worker thread emits -> Qt queues it ->
UI thread handles it. No manual locking needed for UI updates.
"""
import os
import threading
from PyQt6.QtCore import QObject, pyqtSignal

from asytrator import config
from asytrator.capture.video import VideoCapture
from asytrator.capture.audio import AudioCapture
from asytrator.virtual_cam import VirtualCamOutput
from asytrator.dubbing.manager import DubbingManager
from asytrator.audio_output import AudioPlayer, LivePassthrough
from asytrator.media_io import save_video_frames, save_audio, merge_audio_video, load_video, extract_audio


class AppController(QObject):
    # Signals — the UI connects to these.
    status_message = pyqtSignal(str)
    recording_changed = pyqtSignal(bool)     # True = currently recording
    recording_ready = pyqtSignal(bool)       # True = a saved recording exists
    dubbing_ready = pyqtSignal(bool)         # True = dubbed video loaded
    dubbing_in_progress = pyqtSignal(bool)
    playback_finished = pyqtSignal()
    session_loading = pyqtSignal(bool)       # True = loading previous session

    def __init__(self):
        super().__init__()
        os.makedirs(config.MEDIA_DIR, exist_ok=True)

        self.video = VideoCapture()
        self.audio = AudioCapture()
        self.vcam = VirtualCamOutput(self.video)
        self.dubbing = DubbingManager()
        self.audio_out = AudioPlayer(device=config.AUDIO_OUTPUT_DEVICE)
        self.passthrough = LivePassthrough()  # mic → CABLE Input during LIVE mode

        self._has_recording = False
        self._has_dubbing = False
        self._dubbing_running = False
        self._recorded_frames = []
        self._dubbed_frames = []
        self._dubbed_audio = None

    def start(self):
        self.video.start()
        self.audio.start_stream()
        self.vcam.start()
        self.passthrough.start()   # live mic → CABLE Input from the very first moment
        self.status_message.emit("Ready. Click 'Start Recording' to begin.")

    def stop(self):
        self.passthrough.stop()
        self.audio_out.stop()
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
        # Stop passthrough — during recording the cover loop is showing and we
        # don't want the unprocessed live voice going into Teams.
        self.passthrough.stop()

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
        self._dubbed_audio = None
        self.recording_ready.emit(False)
        self.dubbing_ready.emit(False)
        self.recording_changed.emit(True)
        self.status_message.emit("Recording — cover loop active, mic muted in Teams.")

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
        # Back to live — resume passthrough so Teams hears you again.
        self.passthrough.start()

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
        self._dubbed_audio = self._load_dubbed_audio()
        self.dubbing_in_progress.emit(False)
        self.dubbing_ready.emit(True)
        self.status_message.emit("Dubbing complete. Press 'Play' to send to virtual cam.")

    def _load_dubbed_audio(self):
        """Extract audio from the dubbed MP4. Returns None on failure (silent fallback)."""
        try:
            return extract_audio(config.DUBBED_OUTPUT)
        except Exception as e:
            self.status_message.emit(f"Warning: could not extract dubbed audio ({e})")
            return None

    def _on_dubbing_error(self, err):
        self._dubbing_running = False
        self.dubbing_in_progress.emit(False)
        self.status_message.emit(f"Dubbing failed: {err}")

    # --- Session recovery ---

    def load_previous_session(self):
        """Load recording and/or dubbed video left on disk from a prior session."""
        if self.video.is_recording or self._dubbing_running:
            self.status_message.emit("Cannot load previous session while recording or dubbing.")
            return
        threading.Thread(target=self._load_session_worker, daemon=True).start()

    def _load_session_worker(self):
        self.session_loading.emit(True)
        found = []

        if os.path.exists(config.RECORD_OUTPUT):
            self.status_message.emit("Loading previous recording...")
            try:
                frames = load_video(config.RECORD_OUTPUT)
                self._recorded_frames = frames
                self._has_recording = True
                self.recording_ready.emit(True)
                found.append(f"recording ({len(frames) // config.FPS}s)")
            except Exception as e:
                self.status_message.emit(f"Failed to load recording: {e}")

        if os.path.exists(config.DUBBED_OUTPUT):
            self.status_message.emit("Loading previous dubbed video...")
            try:
                frames = load_video(config.DUBBED_OUTPUT)
                self._dubbed_frames = frames
                self._dubbed_audio = self._load_dubbed_audio()
                self._has_dubbing = True
                self.dubbing_ready.emit(True)
                found.append(f"dubbed video ({len(frames) // config.FPS}s)")
            except Exception as e:
                self.status_message.emit(f"Failed to load dubbed video: {e}")

        self.session_loading.emit(False)
        if found:
            self.status_message.emit(f"Previous session restored: {', '.join(found)}.")
        else:
            self.status_message.emit("No previous session found in Media/ folder.")

    # --- Playback ---

    def start_playback(self):
        if not self._has_dubbing:
            self.status_message.emit("No dubbed video yet.")
            return
        # Stop live passthrough — dubbed audio takes over the CABLE Input channel.
        self.passthrough.stop()
        # Start audio first so it's already open when the first vcam frame fires.
        if self._dubbed_audio is not None:
            self.audio_out.play(self._dubbed_audio, config.SAMPLE_RATE)
        self.vcam.set_playback(self._dubbed_frames, on_done=self._on_playback_done)
        device_name = config.AUDIO_OUTPUT_DEVICE or "default output"
        self.status_message.emit(
            f"Playing dubbed video in virtual cam, audio → {device_name}."
        )

    def _on_playback_done(self):
        self.audio_out.stop()
        self.passthrough.start()   # hand CABLE Input back to live mic
        self.playback_finished.emit()
