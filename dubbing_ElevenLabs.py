import os
import time
import requests
from elevenlabs import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# Statuses that mean "still working, keep polling"
IN_PROGRESS_STATUSES = {"dubbing", "preparing"}

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
        elif metadata.status in IN_PROGRESS_STATUSES:
            print(f"  status: {metadata.status}...")
            time.sleep(10)
        else:
            raise Exception(f"Dubbing failed: status='{metadata.status}', response={metadata}")

    # Download result via direct HTTP request to ElevenLabs REST API
    # The SDK's get_dubbed_file / download_video methods have inconsistent naming across versions,
    # so we use the REST endpoint directly to avoid SDK version issues.
    print("Downloading dubbed video...")
    api_key = os.getenv("ELEVENLABS_API_KEY")
    url = f"https://api.elevenlabs.io/v1/dubbing/{dubbing_id}/audio/{target_lang}"
    headers = {"xi-api-key": api_key}
    dl_response = requests.get(url, headers=headers, stream=True)

    if dl_response.status_code != 200:
        raise Exception(f"Download failed: {dl_response.status_code} {dl_response.text}")

    with open(output_path, "wb") as f:
        for chunk in dl_response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Saved: {output_path}")
    return output_path