import os
import time
from elevenlabs import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

def dub_video(input_path, source_lang, target_lang, output_path):
    """
    Sends a local video to ElevenLabs and returns the path
    to the finished dubbed video.
    """
    print(f"Uploading {input_path}...")
    with open(input_path, "rb") as f:
        response = client.dubbing.dub_a_video_or_an_audio_file(
            file=(os.path.basename(input_path), f, "video/mp4"),
            source_lang=source_lang,   # e.g. "de"
            target_lang=target_lang,   # e.g. "en"
        )

    dubbing_id = response.dubbing_id
    print(f"Dubbing started, ID: {dubbing_id}")

    # Poll until finished
    print("Waiting for ElevenLabs...")
    for _ in range(120):  # max 20 minutes
        metadata = client.dubbing.get_dubbing_project_metadata(dubbing_id)
        if metadata.status == "dubbed":
            print("Done!")
            break
        elif metadata.status == "dubbing":
            print("  still working...")
            time.sleep(10)
        else:
            raise Exception(f"Dubbing failed: {metadata.error_message}")

    # Download result
    audio = client.dubbing.get_dubbed_file(dubbing_id, target_lang)
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)
    print(f"Saved: {output_path}")
    return output_path


# HeyGen API Call for dubbing with lipsync (kept for reference):
#
# curl --request POST \
#      --url https://api.heygen.com/v2/video_translate \
#      --header 'accept: application/json' \
#      --header 'content-type: application/json' \
#      --header 'x-api-key: <your-api-key>' \
#      --data '
# {
#   "translate_audio_only": false,
#   "keep_the_same_format": false,
#   "mode": "fast"
# }
# '