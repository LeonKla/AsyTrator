"""Pure I/O helpers: read/write video and audio files, merge them with ffmpeg.

These are plain functions — no shared state, no threads. Anything that touches
the filesystem or ffmpeg lives here so the rest of the code stays clean.
"""
import subprocess
import cv2
import numpy as np
import soundfile as sf

from asytrator.config import FPS, WIDTH, HEIGHT, SAMPLE_RATE, CHANNELS


def load_video(path):
    """Read an MP4 from disk and return a list of RGB frames sized to WIDTH x HEIGHT."""
    frames = []
    cap = cv2.VideoCapture(path)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb = cv2.resize(frame_rgb, (WIDTH, HEIGHT))
        frames.append(frame_rgb)
    cap.release()
    print(f"Video loaded: {len(frames)} frames = {len(frames) // FPS}s")
    return frames


def save_video_frames(frames, path):
    """Write RGB frames to a silent MP4."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, FPS, (WIDTH, HEIGHT))
    for frame_rgb in frames:
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        out.write(frame_bgr)
    out.release()
    print(f"Silent video saved: {path} ({len(frames) // FPS}s)")


def save_audio(chunks, path):
    """Concat audio chunks (numpy arrays) and write a WAV."""
    audio_data = np.concatenate(chunks, axis=0)
    sf.write(path, audio_data, SAMPLE_RATE)
    duration = len(audio_data) / SAMPLE_RATE
    print(f"Audio saved: {path} ({duration:.1f}s, {len(audio_data)} samples)")


def extract_audio(path):
    """Extract audio from a video file as a float32 numpy array.

    Uses ffmpeg to decode to raw PCM so we don't need an extra audio library.
    Returns shape (N,) for mono or (N, channels) for stereo.
    """
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", path,
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ac", str(CHANNELS),
        "-ar", str(SAMPLE_RATE),
        "pipe:1",
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    audio = np.frombuffer(result.stdout, dtype=np.float32)
    if CHANNELS > 1:
        audio = audio.reshape(-1, CHANNELS)
    duration = len(audio) / SAMPLE_RATE
    print(f"Audio extracted: {path} ({duration:.1f}s)")
    return audio


def merge_audio_video(video_path, audio_path, output_path):
    """Mux a silent video with a WAV into a single MP4 (H.264 / AAC)."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ], check=True, capture_output=True)
    print(f"Merged video saved: {output_path}")
