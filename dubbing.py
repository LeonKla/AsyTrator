import os
import time
from elevenlabs import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

def dub_video(input_path, source_lang, target_lang, output_path):
    """
    Sends a local video to ElevenLabs dubbing API and saves the result.
    ElevenLabs handles transcription, translation, and voice synthesis automatically.
    source_lang / target_lang: ISO 639-1 codes, e.g. "de", "en", "es"
    """
    print(f"Uploading {input_path}...")
    with open(input_path, "rb") as f:
        response = client.dubbing.create(
            file=(os.path.basename(input_path), f, "video/mp4"),
            source_lang=source_lang,
            target_lang=target_lang,
            watermark=True,
        )

    dubbing_id = response.dubbing_id
    print(f"Dubbing started, ID: {dubbing_id}")

    # Poll until finished
    print("Waiting for ElevenLabs...")
    for _ in range(120):  # max 20 minutes
        metadata = client.dubbing.get(dubbing_id)
        if metadata.status == "dubbed":
            print("Done!")
            break
        elif metadata.status == "dubbing":
            print("  still working...")
            time.sleep(10)
        else:
            raise Exception(f"Dubbing failed: status={metadata.status}, details={metadata}")

    # Download result
    audio = client.dubbing.get_dubbed_file(dubbing_id, target_lang)
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    print(f"Saved: {output_path}")
    return output_path