"""Audio output helpers: playback and live passthrough to a virtual audio device.

Two classes live here:

    AudioPlayer      — plays a pre-loaded float32 numpy array to a specific output
                       device (e.g. VB-Audio CABLE Input) without blocking any
                       other thread.

    LivePassthrough  — continuously routes microphone input to an output device in
                       real time using two separate streams + a small queue.
                       Used to keep the live mic audible in Teams during LIVE mode.

Why two streams instead of sd.Stream (duplex)?
On Windows, the microphone (e.g. Realtek WDM) and VB-Audio CABLE can use
different driver models. A single duplex sd.Stream requires both devices to share
the same host API, which often fails. Two separate streams connected via a small
in-memory queue is more reliable and still low-latency.

Why no lock in AudioPlayer._callback?
Audio callbacks run in a high-priority OS audio thread. Acquiring a Python
threading.Lock there risks priority-inversion stalls and silent drops. Instead we
rely on the fact that play() always calls stop() (which closes the stream) before
replacing self._data — so the callback thread is guaranteed to be gone before the
data pointer changes.
"""
import queue
import sounddevice as sd
import numpy as np

from asytrator import config


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------

def resolve_output_device(device):
    """Return a sounddevice device index for *device*.

    Accepts:
    - None  → system default output
    - int   → used as-is
    - str   → case-insensitive substring match against output-capable devices;
              falls back to the raw string if nothing matches (sd accepts names)
    """
    if device is None or isinstance(device, int):
        return device
    devices = sd.query_devices()
    name_lower = device.lower()
    for i, dev in enumerate(devices):
        if dev["max_output_channels"] > 0 and name_lower in dev["name"].lower():
            print(f"Audio output resolved: '{device}' → [{i}] {dev['name']}")
            return i
    print(f"Audio output: no device matched '{device}', passing name to sounddevice directly")
    return device


# ---------------------------------------------------------------------------
# AudioPlayer — play a dubbed audio array to CABLE Input
# ---------------------------------------------------------------------------

class AudioPlayer:
    """Non-blocking playback of a float32 numpy array to a named output device."""

    def __init__(self, device=None):
        """
        device: device index, name substring (e.g. "CABLE Input"), or None for default.
        """
        self._device = device
        self._stream = None
        self._data: np.ndarray | None = None
        self._position = 0

    def play(self, audio_data: np.ndarray, samplerate: int):
        """Start playing *audio_data*. Stops any currently playing audio first."""
        self.stop()  # guarantees callback thread is done before we replace _data

        channels = audio_data.shape[1] if audio_data.ndim > 1 else 1
        # (N, channels) shape required by the OutputStream callback
        self._data = audio_data.reshape(-1, channels).astype(np.float32)
        self._position = 0

        device = resolve_output_device(self._device)
        try:
            self._stream = sd.OutputStream(
                samplerate=samplerate,
                channels=channels,
                dtype="float32",
                device=device,
                callback=self._callback,
                finished_callback=self._on_finished,
            )
            self._stream.start()
            print(f"AudioPlayer: playing {len(self._data) / samplerate:.1f}s → device {device}")
        except Exception as e:
            print(f"AudioPlayer: failed to open output stream ({e})")
            self._stream = None

    def stop(self):
        """Stop playback immediately and release the stream."""
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    # -- audio thread callback (no Python locks allowed here) ---------------

    def _callback(self, outdata, frames, time_info, status):
        data = self._data          # read reference once — safe, stop() closed stream first
        pos = self._position
        if data is None:
            outdata[:] = 0
            raise sd.CallbackStop()
        remaining = len(data) - pos
        if remaining <= 0:
            outdata[:] = 0
            raise sd.CallbackStop()
        chunk = min(frames, remaining)
        outdata[:chunk] = data[pos : pos + chunk]
        if chunk < frames:
            outdata[chunk:] = 0
        self._position = pos + chunk  # only this thread writes _position

    def _on_finished(self):
        self._stream = None


# ---------------------------------------------------------------------------
# LivePassthrough — route microphone → CABLE Input in real time
# ---------------------------------------------------------------------------

class LivePassthrough:
    """Continuously forwards mic audio to a virtual output device.

    Start it when the virtual cam is in LIVE mode so Teams keeps hearing you.
    Stop it before playback (dubbed audio takes over) and before recording
    (cover loop mode — you don't want your unprocessed voice going through).
    """

    # 4 blocks of headroom before we start dropping; keeps latency under ~46 ms
    # at 44100 Hz / 512 blocksize.
    _QUEUE_MAXSIZE = 4
    _BLOCKSIZE = 512

    def __init__(self, input_device=None, output_device=None,
                 samplerate=None, channels=None):
        self._input_device = input_device if input_device is not None else config.MICROPHONE_DEVICE
        self._output_device = output_device if output_device is not None else config.AUDIO_OUTPUT_DEVICE
        self._samplerate = samplerate or config.SAMPLE_RATE
        self._channels = channels or config.CHANNELS
        self._q: queue.Queue | None = None
        self._in_stream = None
        self._out_stream = None

    def start(self):
        if self._in_stream is not None:
            return  # already running
        out_device = resolve_output_device(self._output_device)
        self._q = queue.Queue(maxsize=self._QUEUE_MAXSIZE)
        try:
            self._in_stream = sd.InputStream(
                device=self._input_device,
                samplerate=self._samplerate,
                channels=self._channels,
                dtype="float32",
                blocksize=self._BLOCKSIZE,
                callback=self._in_callback,
            )
            self._out_stream = sd.OutputStream(
                device=out_device,
                samplerate=self._samplerate,
                channels=self._channels,
                dtype="float32",
                blocksize=self._BLOCKSIZE,
                callback=self._out_callback,
            )
            self._in_stream.start()
            self._out_stream.start()
            print(f"LivePassthrough: mic[{self._input_device}] → output[{out_device}]")
        except Exception as e:
            print(f"LivePassthrough: failed to start ({e})")
            self._teardown()

    def stop(self):
        self._teardown()

    def update_output_device(self, device):
        """Hot-swap the output device (called when user changes dropdown)."""
        was_running = self._in_stream is not None
        self.stop()
        self._output_device = device
        if was_running:
            self.start()

    # -- audio thread callbacks (no Python locks) ---------------------------

    def _in_callback(self, indata, frames, time_info, status):
        try:
            self._q.put_nowait(indata.copy())
        except queue.Full:
            pass  # drop oldest-ish block rather than block the audio thread

    def _out_callback(self, outdata, frames, time_info, status):
        try:
            outdata[:] = self._q.get_nowait()
        except queue.Empty:
            outdata[:] = 0  # underrun — output silence, not a crash

    # -- private ------------------------------------------------------------

    def _teardown(self):
        for stream in (self._in_stream, self._out_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._in_stream = None
        self._out_stream = None
        self._q = None
