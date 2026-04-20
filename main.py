import sys
import io
import cv2
import pyvirtualcam
import threading
from collections import deque
from dotenv import load_dotenv
from dubbing import dub_video

# Fix for Python 3.14 + Windows terminal unicode bug
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')

load_dotenv()

# --- Constants ---
FPS = 30
WIDTH = 1280
HEIGHT = 720
RECORD_OUTPUT = "input_video.mp4"

# --- Shared State ---
frame_buffer = deque(maxlen=1800)   # ~1 minute of buffer at 30fps
mode = "LIVE"                        # "LIVE" | "LOOP" | "PLAYBACK"
lock = threading.Lock()

frozen_loop = []        # frames frozen at the moment recording started
playback_frames = []    # translated video frames, ready after dubbing
loop_index = 0
playback_index = 0

# --- Recording State ---
is_recording = False
recorded_frames = []
recording_ready = False  # True once a recording has been saved and is ready to dub
dubbing_ready = False    # True once dubbing has finished and playback is available


def load_video(path):
    """Loads a video file and returns a list of RGB frames"""
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


def save_recorded_frames(frames, path):
    """Saves a list of RGB frames to an MP4 file"""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, FPS, (WIDTH, HEIGHT))
    for frame_rgb in frames:
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        out.write(frame_bgr)
    out.release()
    print(f"Recording saved: {path} ({len(frames) // FPS}s)")


def capture_thread(cap):
    """Continuously reads webcam frames into the shared buffer.
    Also appends to recorded_frames when recording is active."""
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb = cv2.resize(frame_rgb, (WIDTH, HEIGHT))
        with lock:
            frame_buffer.append(frame_rgb)
            if is_recording:
                recorded_frames.append(frame_rgb.copy())


def dubbing_thread(video_path, source_lang, target_lang):
    """Runs dubbing in the background. Sets dubbing_ready when done."""
    global playback_frames, playback_index, dubbing_ready
    output_path = "translated_output.mp4"
    try:
        dub_video(video_path, source_lang, target_lang, output_path)
        frames = load_video(output_path)
        with lock:
            playback_frames = frames
            playback_index = 0
            dubbing_ready = True
        print(">> Dubbing complete! Press 'p' to start playback.")
    except Exception as e:
        print(f"Dubbing failed: {e}")


def switch_mode():
    """Keyboard command handler running in its own thread."""
    global mode, frozen_loop, loop_index, playback_index
    global is_recording, recorded_frames, recording_ready, dubbing_ready

    print_help()

    while True:
        cmd = input().strip().lower()

        with lock:
            if cmd == "r":
                if not is_recording:
                    # Start recording — freeze loop as cover screen
                    is_recording = True
                    recorded_frames = []
                    frozen_loop = list(frame_buffer)
                    loop_index = 0
                    mode = "LOOP"
                    print(f">> Recording started — camera showing loop as cover. Press 'r' to stop.")
                else:
                    # Stop recording — return to LIVE
                    is_recording = False
                    frames_to_save = list(recorded_frames)
                    recorded_frames = []
                    mode = "LIVE"
                    recording_ready = False  # reset until save completes
                    dubbing_ready = False
                    print(f">> Recording stopped ({len(frames_to_save) // FPS}s). Saving... camera back to LIVE.")

                    # Save in background so we don't block
                    def save_and_flag():
                        global recording_ready
                        save_recorded_frames(frames_to_save, RECORD_OUTPUT)
                        with lock:
                            recording_ready = True
                        print(">> Recording ready. Press 'd' to start dubbing.")
                    threading.Thread(target=save_and_flag, daemon=True).start()

            elif cmd == "d":
                if not recording_ready:
                    print("No recording available yet — press 'r' to record first.")
                elif dubbing_ready:
                    print("Dubbing already done — press 'p' to play, or record again with 'r'.")
                else:
                    source = input("  Source language (e.g. de, en, es, fr): ").strip().lower()
                    target = input("  Target language (e.g. en, de, es, fr): ").strip().lower()
                    if not source or not target:
                        print("Invalid input, dubbing cancelled.")
                    else:
                        print(f">> Starting dubbing in background ({source} → {target})...")
                        threading.Thread(
                            target=dubbing_thread,
                            args=(RECORD_OUTPUT, source, target),
                            daemon=True
                        ).start()

            elif cmd == "p":
                if not dubbing_ready:
                    if not recording_ready:
                        print("Nothing recorded yet — press 'r' to record.")
                    else:
                        print("Dubbing not finished yet — wait for it to complete.")
                else:
                    mode = "PLAYBACK"
                    playback_index = 0
                    print(">> PLAYBACK started.")

            elif cmd == "h":
                print_help()

            else:
                print(f"Unknown command '{cmd}' — press 'h' for help.")


def print_help():
    print("\nCommands:")
    print("  r  — start / stop recording (loop covers camera while recording; Wait at least 30 seconds)")
    print("  d  — start dubbing (only available after recording)")
    print("  p  — play translated video (only available after dubbing finishes)")
    print("  h  — show this help\n")


# --- Start ---
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

t_capture = threading.Thread(target=capture_thread, args=(cap,), daemon=True)
t_switch = threading.Thread(target=switch_mode, daemon=True)
t_capture.start()
t_switch.start()

with pyvirtualcam.Camera(width=WIDTH, height=HEIGHT, fps=FPS) as vcam:
    print(f"Virtual camera started: {vcam.device}")
    while True:
        with lock:
            current_mode = mode
            if current_mode == "LIVE":
                snapshot = list(frame_buffer)
            elif current_mode == "LOOP":
                snapshot = frozen_loop
            else:
                snapshot = playback_frames

        if not snapshot:
            continue

        if current_mode == "LIVE":
            vcam.send(snapshot[-1])
        elif current_mode == "LOOP":
            vcam.send(snapshot[loop_index % len(snapshot)])
            loop_index += 1
        elif current_mode == "PLAYBACK":
            vcam.send(snapshot[playback_index % len(snapshot)])
            playback_index += 1

        vcam.sleep_until_next_frame()