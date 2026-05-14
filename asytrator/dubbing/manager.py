"""Background dubbing job.

Wraps the chosen dubbing provider in a thread so the UI doesn't freeze.
The callback is invoked from the worker thread with either the loaded RGB
frames or an error.
"""
import threading

from asytrator.dubbing import elevenlabs, heygen
from asytrator.media_io import load_video
from asytrator.config import DUBBED_OUTPUT


class DubbingManager:
    def run_async(self, video_path, source_lang, target_lang, provider, on_success, on_error):
        threading.Thread(
            target=self._worker,
            args=(video_path, source_lang, target_lang, provider, on_success, on_error),
            daemon=True,
        ).start()

    def _worker(self, video_path, source_lang, target_lang, provider, on_success, on_error):
        try:
            if provider == "heygen":
                heygen.dub_video(video_path, source_lang, target_lang, DUBBED_OUTPUT)
            else:
                elevenlabs.dub_video(video_path, source_lang, target_lang, DUBBED_OUTPUT)
            frames = load_video(DUBBED_OUTPUT)
            on_success(frames)
        except Exception as e:
            on_error(e)
