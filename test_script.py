import cv2
import pyvirtualcam
import threading
from collections import deque

# --- Shared State ---
frame_buffer = deque(maxlen=1800)  # 60 Sekunden bei 30fps
mode = "LIVE"  # "LIVE" oder "LOOP"
lock = threading.Lock()

def capture_thread(cap):
    """Liest immer von der Webcam und füllt den Buffer"""
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb = cv2.resize(frame_rgb, (1280, 720))
        with lock:
            frame_buffer.append(frame_rgb)

frozen_loop = [] 

def switch_mode():
    global mode, frozen_loop, loop_index
    while True:
        input()
        with lock:
            if mode == "LIVE":
                mode = "LOOP"
                frozen_loop = list(frame_buffer)
                loop_index = 0  # ← zurücksetzen
                print(f">> LOOP ({len(frozen_loop)} frames = {len(frozen_loop)//30}s)")
            else:
                mode = "LIVE"
                frozen_loop = []
                print(">> LIVE")

# --- Start ---
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

t_capture = threading.Thread(target=capture_thread, args=(cap,), daemon=True)
t_switch = threading.Thread(target=switch_mode, daemon=True)
t_capture.start()
t_switch.start()

print("Running — drück Enter zum Umschalten zwischen LIVE und LOOP")

loop_index = 0
with pyvirtualcam.Camera(width=1280, height=720, fps=30) as vcam:
    while True:
        with lock:
            current_mode = mode
            snapshot = frozen_loop if current_mode == "LOOP" else list(frame_buffer)

        if not snapshot:
            continue

        if current_mode == "LIVE":
            vcam.send(snapshot[-1])
        elif current_mode == "LOOP":
            vcam.send(snapshot[loop_index % len(snapshot)])
            loop_index += 1

        vcam.sleep_until_next_frame()