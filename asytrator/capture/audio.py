"""Microphone capture via sounddevice.

The InputStream runs continuously; we only append chunks while is_recording is
True. That avoids the latency of starting/stopping the stream on every record.
"""
import sounddevice as sd

from asytrator.config import SAMPLE_RATE, CHANNELS, MICROPHONE_DEVICE


class AudioCapture:
    def __init__(self):
        self.is_recording = False
        self.chunks = []
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            device=MICROPHONE_DEVICE,
            callback=self._on_chunk,
        )

    def _on_chunk(self, indata, frames, time, status):
        if status:
            print(f"  Audio status: {status}")
        if self.is_recording:
            self.chunks.append(indata.copy())

    def start_stream(self):
        self.stream.start()

    def stop_stream(self):
        self.stream.stop()
        self.stream.close()

    def begin_recording(self):
        self.chunks = []
        self.is_recording = True

    def end_recording(self):
        self.is_recording = False
        chunks = self.chunks
        self.chunks = []
        return chunks
