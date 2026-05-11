"""Webcam capture in a background thread.

Reads frames continuously into a rolling buffer (the last ~60s) and, when
recording is active, also appends them to a separate recorded_frames list.
"""
import threading
from collections import deque
import cv2

from asytrator.config import WIDTH, HEIGHT, FPS, WEBCAM_DEVICE, BUFFER_SECONDS


class VideoCapture:
    def __init__(self):
        self.cap = cv2.VideoCapture(WEBCAM_DEVICE)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

        self.frame_buffer = deque(maxlen=FPS * BUFFER_SECONDS)
        self.recorded_frames = []
        self.is_recording = False

        self.lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop = True
        self.cap.release()

    def _run(self):
        while not self._stop:
            ret, frame = self.cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb = cv2.resize(frame_rgb, (WIDTH, HEIGHT))
            with self.lock:
                self.frame_buffer.append(frame_rgb)
                if self.is_recording:
                    self.recorded_frames.append(frame_rgb.copy())

    def latest_frame(self):
        """Most recent webcam frame, or None if buffer empty."""
        with self.lock:
            return self.frame_buffer[-1] if self.frame_buffer else None

    def snapshot_buffer(self):
        """Copy of the rolling buffer (used as 'cover loop' while recording)."""
        with self.lock:
            return list(self.frame_buffer)

    def begin_recording(self):
        with self.lock:
            self.recorded_frames = []
            self.is_recording = True

    def end_recording(self):
        """Stop recording and return the captured frames."""
        with self.lock:
            self.is_recording = False
            frames = self.recorded_frames
            self.recorded_frames = []
            return frames
