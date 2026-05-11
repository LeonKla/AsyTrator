"""Virtual camera output loop.

Runs in its own thread (so the PyQt6 UI thread stays responsive) and pushes
one frame per tick to the virtual camera driver. Mode decides which source:

    LIVE     -> most recent webcam frame
    LOOP     -> a frozen list of frames, played as a *pendulum*
                (forward to end, reverse to start, forward again, ...)
                so the loop point has no visible cut
    PLAYBACK -> the dubbed video, played once forward
"""
import threading
import time
import pyvirtualcam

from asytrator.config import WIDTH, HEIGHT, FPS


class VirtualCamOutput:
    LIVE = "LIVE"
    LOOP = "LOOP"
    PLAYBACK = "PLAYBACK"

    def __init__(self, video_capture):
        self.video_capture = video_capture
        self.mode = self.LIVE

        self.loop_frames = []
        self.loop_index = 0
        self.loop_direction = 1  # +1 forward, -1 backward (pendulum)

        self.playback_frames = []
        self.playback_index = 0
        self.playback_done_callback = None

        self.lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop = True

    def set_live(self):
        with self.lock:
            self.mode = self.LIVE

    def set_loop(self, frames):
        with self.lock:
            self.loop_frames = frames
            self.loop_index = 0
            self.loop_direction = 1
            self.mode = self.LOOP

    def set_playback(self, frames, on_done=None):
        with self.lock:
            self.playback_frames = frames
            self.playback_index = 0
            self.playback_done_callback = on_done
            self.mode = self.PLAYBACK

    def _next_pendulum_frame(self):
        """Return current loop frame, then advance the index using pendulum rules.

        Pendulum: when we hit the last frame, flip direction to backwards;
        when we hit the first frame, flip back to forwards. This way the
        playback eases through the seam instead of cutting.
        """
        frames = self.loop_frames
        n = len(frames)
        if n == 0:
            return None
        if n == 1:
            return frames[0]

        frame = frames[self.loop_index]

        # Flip direction at the endpoints *before* stepping, so each endpoint
        # frame plays exactly once per cycle (no doubled frame on reversal).
        if self.loop_index >= n - 1:
            self.loop_direction = -1
        elif self.loop_index <= 0:
            self.loop_direction = 1
        self.loop_index += self.loop_direction
        return frame

    def _run(self):
        with pyvirtualcam.Camera(width=WIDTH, height=HEIGHT, fps=FPS) as vcam:
            print(f"Virtual camera started: {vcam.device}")
            frame_duration = 1.0 / FPS
            while not self._stop:
                frame, done_cb = self._next_output_frame()
                if frame is not None:
                    vcam.send(frame)
                    vcam.sleep_until_next_frame()
                else:
                    # Webcam hasn't produced a frame yet — sleep_until_next_frame
                    # crashes if send() was never called, so sleep manually.
                    time.sleep(frame_duration)
                if done_cb is not None:
                    done_cb()

    def _next_output_frame(self):
        """Pick the right frame for the current mode. Returns (frame, done_cb)."""
        with self.lock:
            mode = self.mode
            if mode == self.LIVE:
                return self.video_capture.latest_frame(), None

            if mode == self.LOOP:
                return self._next_pendulum_frame(), None

            # PLAYBACK
            frames = self.playback_frames
            if not frames:
                return None, None
            if self.playback_index >= len(frames):
                # finished — bounce back to LIVE and fire the callback once
                self.mode = self.LIVE
                cb = self.playback_done_callback
                self.playback_done_callback = None
                return frames[-1], cb
            frame = frames[self.playback_index]
            self.playback_index += 1
            return frame, None
