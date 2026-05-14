"""HeyGen Video Translation provider — uploads a video, polls until done, downloads.

HeyGen produces higher-quality dubbing with lip-sync at higher cost.
Uses the v2 Video Translate API: https://docs.heygen.com/reference/video-translate
"""
import os
import time
import requests

_BASE = "https://api.heygen.com"

# HeyGen expects full language names, not ISO codes.
_ISO_TO_HEYGEN = {
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "tr": "Turkish",
    "hi": "Hindi",
}


def _headers():
    key = os.getenv("HEYGEN_API_KEY")
    if not key:
        raise EnvironmentError("HEYGEN_API_KEY is not set in environment / .env file.")
    return {"X-Api-Key": key}


def _resolve_lang(code: str) -> str:
    name = _ISO_TO_HEYGEN.get(code.lower())
    if not name:
        raise ValueError(
            f"Unknown language code '{code}' for HeyGen. "
            f"Supported codes: {', '.join(_ISO_TO_HEYGEN)}"
        )
    return name


def dub_video(input_path: str, source_lang: str, target_lang: str, output_path: str) -> str:
    """
    Sends a local video to HeyGen Video Translate API and saves the result.
    source_lang / target_lang: ISO 639-1 codes, e.g. "de", "en"
    """
    target_name = _resolve_lang(target_lang)

    print(f"Uploading {input_path} to HeyGen...")
    with open(input_path, "rb") as f:
        resp = requests.post(
            f"{_BASE}/v2/video_translate",
            headers=_headers(),
            files={"video": (os.path.basename(input_path), f, "video/mp4")},
            data={"output_language": target_name, "title": "AsyTrator dubbing"},
            timeout=120,
        )

    if resp.status_code != 200:
        raise Exception(f"HeyGen upload failed: {resp.status_code} {resp.text}")

    body = resp.json()
    job_id = body.get("data", {}).get("video_translate_id")
    if not job_id:
        raise Exception(f"HeyGen returned no job ID: {body}")

    print(f"HeyGen job started, ID: {job_id}")

    for _ in range(120):  # max 20 minutes
        time.sleep(10)
        poll = requests.get(
            f"{_BASE}/v2/video_translate/{job_id}",
            headers=_headers(),
            timeout=30,
        )
        if poll.status_code != 200:
            raise Exception(f"HeyGen poll failed: {poll.status_code} {poll.text}")

        data = poll.json().get("data", {})
        status = data.get("status")
        print(f"  status: {status}...")

        if status == "completed":
            download_url = data.get("url")
            if not download_url:
                raise Exception("HeyGen completed but returned no download URL.")
            break
        elif status == "failed":
            raise Exception(f"HeyGen dubbing failed: {data}")

    else:
        raise Exception("HeyGen dubbing timed out after 20 minutes.")

    print("Downloading dubbed video from HeyGen...")
    dl = requests.get(download_url, stream=True, timeout=120)
    if dl.status_code != 200:
        raise Exception(f"HeyGen download failed: {dl.status_code}")

    with open(output_path, "wb") as f:
        for chunk in dl.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Saved: {output_path}")
    return output_path
