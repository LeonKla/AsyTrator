import cv2
import pyvirtualcam
import threading
from collections import deque
from dotenv import load_dotenv
from dubbing import dub_video  # your dubbing.py

load_dotenv()

# --- Shared State ---
frame_buffer = deque(maxlen=1800)  # ~1 minute of buffer at 30fps
mode = "LIVE"  # "LIVE" | "LOOP" | "PLAYBACK"
lock = threading.Lock()
frozen_loop = []
playback_frames = []
loop_index = 0
playback_index = 0

def load_video(path):
    """Loads a video file and returns a list of RGB frames"""
    frames = []
    cap = cv2.VideoCapture(path)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb = cv2.resize(frame_rgb, (1280, 720))
        frames.append(frame_rgb)
    cap.release()
    print(f"Video loaded: {len(frames)} frames = {len(frames)//30}s")
    return frames

def capture_thread(cap):
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb = cv2.resize(frame_rgb, (1280, 720))
        with lock:
            frame_buffer.append(frame_rgb)

def dubbing_thread(video_path, source_lang, target_lang):
    """Runs in the background — calls ElevenLabs and switches to PLAYBACK when done"""
    global mode, playback_frames, playback_index
    output_path = "translated_output.mp4"
    try:
        dub_video(video_path, source_lang, target_lang, output_path)
        frames = load_video(output_path)
        with lock:
            playback_frames = frames
            playback_index = 0
            mode = "PLAYBACK"
            print(">> PLAYBACK started")
    except Exception as e:
        print(f"Dubbing failed: {e}")
        with lock:
            mode = "LIVE"

def switch_mode():
    global mode, frozen_loop, loop_index, playback_index
    print("Commands: Enter = LOOP/LIVE, 'p' + Enter = PLAYBACK, 'd' + Enter = start dubbing")
    while True:
        cmd = input().strip().lower()

        with lock:
            if cmd == "":  # Enter alone
                if mode == "LIVE":
                    mode = "LOOP"
                    frozen_loop = list(frame_buffer)
                    loop_index = 0
                    print(f">> LOOP ({len(frozen_loop)//30}s)")
                elif mode == "LOOP":
                    mode = "LIVE"
                    frozen_loop = []
                    print(">> LIVE")

            elif cmd == "p":
                if playback_frames:
                    mode = "PLAYBACK"
                    playback_index = 0
                    print(">> PLAYBACK")
                else:
                    print("No video loaded — press 'd' first")

            elif cmd == "d":
                if mode == "LIVE":
                    mode = "LOOP"
                    frozen_loop = list(frame_buffer)
                    loop_index = 0
                    print(">> LOOP active, dubbing running in background...")
                    # Start dubbing in its own thread
                    t = threading.Thread(
                        target=dubbing_thread,
                        args=("input_video.mp4", "de", "en"),  # <- your values here
                        daemon=True
                    )
                    t.start()
                else:
                    print("Can only start from LIVE mode")

# --- Start ---
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

t_capture = threading.Thread(target=capture_thread, args=(cap,), daemon=True)
t_switch = threading.Thread(target=switch_mode, daemon=True)
t_capture.start()
t_switch.start()

with pyvirtualcam.Camera(width=1280, height=720, fps=30) as vcam:
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