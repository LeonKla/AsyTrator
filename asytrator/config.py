"""Central configuration. Edit values here, not scattered through the code."""
import os

FPS = 30
WIDTH = 1280
HEIGHT = 720
SAMPLE_RATE = 44100
CHANNELS = 1

MEDIA_DIR = "Media"
RECORD_VIDEO = os.path.join(MEDIA_DIR, "input_video_silent.mp4")
RECORD_AUDIO = os.path.join(MEDIA_DIR, "input_audio.wav")
RECORD_OUTPUT = os.path.join(MEDIA_DIR, "input_video.mp4")
DUBBED_OUTPUT = os.path.join(MEDIA_DIR, "translated_output.mp4")

# Run this to list devices and pick the right index:
#   python -c "import sounddevice; print(sounddevice.query_devices())"
MICROPHONE_DEVICE = 1
WEBCAM_DEVICE = 0

BUFFER_SECONDS = 60
