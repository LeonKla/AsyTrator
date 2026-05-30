# AsyTrator

Speak your native language in a Teams meeting — colleagues hear a real-time dubbed translation.

AsyTrator records a short video of you speaking, sends it to a dubbing API (ElevenLabs or HeyGen), and plays the result back through virtual devices so Teams sees and hears the dubbed version instead of you live. While you record, a seamless loop of your webcam keeps playing in the meeting so nobody notices.

---

## How it works

```
You record yourself  →  API dubs the video  →  Teams sees & hears the dubbed version
```

**Step by step:**

1. **Cover loop** — when you hit Record, AsyTrator freezes your last 60 seconds of webcam footage into a seamless pendulum loop and feeds it to Teams via OBS Virtual Camera. Colleagues see a natural-looking loop while you record your take behind the scenes.

2. **Record** — your webcam and microphone are captured simultaneously. On stop, `ffmpeg` merges them into a single MP4.

3. **Dub** — the MP4 is sent to ElevenLabs (fast, audio-only translation) or HeyGen (slower, with lip-sync). The dubbed MP4 is saved to disk.

4. **Broadcast** — clicking "Broadcast Dubbed" plays the dubbed video frame-by-frame through OBS Virtual Camera (video) and streams the audio track to VB-Audio CABLE Input (audio). Teams picks up CABLE Output as your microphone — colleagues hear the dubbed voice.

---

## Virtual device setup (one-time)

You need two virtual devices installed before running AsyTrator:

| Device | Purpose | Download |
|--------|---------|----------|
| **OBS Virtual Camera** | Video channel into Teams | [obsproject.com](https://obsproject.com) |
| **VB-Audio Virtual Cable** | Audio channel into Teams | [vb-audio.com/Cable](https://vb-audio.com/Cable) |

**In Teams** (before joining a meeting):

- Camera → **OBS Virtual Camera**
- Microphone → **CABLE Output (VB-Audio Virtual Cable)**

---

## Requirements

- Python 3.11+
- `ffmpeg` on PATH — [ffmpeg.org](https://ffmpeg.org/download.html)
- ElevenLabs API key and/or HeyGen API key

Install Python dependencies:

```
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
ELEVENLABS_API_KEY=your_key_here
HEYGEN_API_KEY=your_key_here
```

---

## Running

```
python main.py
```

---

## Device configuration

If the app cannot find your microphone or webcam, edit [`asytrator/config.py`](asytrator/config.py).  
Run this to list available devices and find the right index:

```
python -c "import sounddevice; print(sounddevice.query_devices())"
python -c "import cv2; [print(i, cv2.VideoCapture(i).isOpened()) for i in range(5)]"
```

Then set `MICROPHONE_DEVICE` and `WEBCAM_DEVICE` to the correct indices.

The audio output device (where dubbed audio is sent) can be changed from the UI dropdown at runtime — it defaults to `CABLE Input` which is correct for VB-Audio Virtual Cable.

---

## Architecture

```
main.py
  └─ creates AppController  ← the brain
       ├─ VideoCapture        webcam → rolling frame buffer
       ├─ AudioCapture        microphone → audio chunks
       ├─ VirtualCamOutput    frames → OBS Virtual Camera  (LIVE / LOOP / PLAYBACK)
       ├─ AudioPlayer         audio array → CABLE Input → Teams hears it
       └─ DubbingManager      MP4 → ElevenLabs/HeyGen API → dubbed MP4
  └─ creates MainWindow  ← the UI
       └─ calls controller methods on button clicks
       └─ listens to Qt signals to update labels / enable buttons
```

### File map

| File | Role |
|------|------|
| `main.py` | Entry point — loads env, checks deps, starts Qt app |
| `asytrator/config.py` | All constants: device indices, file paths, FPS, sample rate |
| `asytrator/controller.py` | State machine — owns every component, emits Qt signals |
| `asytrator/ui.py` | Buttons and labels — calls controller, reacts to signals |
| `asytrator/media_io.py` | Pure I/O: read/write video & audio, run ffmpeg |
| `asytrator/virtual_cam.py` | pyvirtualcam thread: LIVE / LOOP / PLAYBACK modes |
| `asytrator/audio_output.py` | sounddevice output stream → CABLE Input |
| `asytrator/capture/video.py` | OpenCV webcam thread, rolling buffer, recording |
| `asytrator/capture/audio.py` | sounddevice mic stream, recording chunks |
| `asytrator/dubbing/manager.py` | Runs dubbing in a background thread, calls provider |
| `asytrator/dubbing/elevenlabs.py` | ElevenLabs API: upload → poll → download |
| `asytrator/dubbing/heygen.py` | HeyGen API: upload → poll → download |
| `asytrator/preview.py` | Qt dialog to preview recorded / dubbed video locally |

### Virtual device flow

```
AsyTrator                    VB-Audio Cable             Teams
──────────────────────────────────────────────────────────────
AudioPlayer.play()  ──→  CABLE Input  ──→  CABLE Output  ──→  Microphone
VirtualCamOutput    ──→  OBS Virtual Camera              ──→  Camera
```

`CABLE Input` is where AsyTrator writes audio.  
`CABLE Output` is what Teams reads as a microphone.  
`OBS Virtual Camera` is the video equivalent.

---

## Dubbing providers

| Provider | Speed | Lip-sync | Notes |
|----------|-------|---------|-------|
| ElevenLabs | Fast (~1 min) | No | Audio track only, original video unchanged |
| HeyGen | Slow (~3–5 min) | Yes | Full face re-render, more expensive |
