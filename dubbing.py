import os
import time
from elevenlabs import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

def dub_video(input_path, source_lang, target_lang, output_path):
    """
    Schickt ein lokales Video an ElevenLabs und gibt den Pfad 
    zum fertigen Video zurück.
    """
    print(f"Uploading {input_path}...")
    with open(input_path, "rb") as f:
        response = client.dubbing.dub_a_video_or_an_audio_file(
            file=(os.path.basename(input_path), f, "video/mp4"),
            source_lang=source_lang,   # z.B. "de"
            target_lang=target_lang,   # z.B. "en"
        )

    dubbing_id = response.dubbing_id
    print(f"Dubbing gestartet, ID: {dubbing_id}")

    # Pollen bis fertig
    print("Warte auf ElevenLabs...")
    for _ in range(120):  # max 20 Minuten
        metadata = client.dubbing.get_dubbing_project_metadata(dubbing_id)
        if metadata.status == "dubbed":
            print("Fertig!")
            break
        elif metadata.status == "dubbing":
            print("  noch am Arbeiten...")
            time.sleep(10)
        else:
            raise Exception(f"Dubbing fehlgeschlagen: {metadata.error_message}")

    # Runterladen
    audio = client.dubbing.get_dubbed_file(dubbing_id, target_lang)
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)
    print(f"Gespeichert: {output_path}")
    return output_path



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