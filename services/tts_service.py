import os
import time
import uuid
import aiohttp
from pathlib import Path

MURF_API_KEY = os.getenv("MURF_API_KEY")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

async def download_url_to_file(url: str, dest: Path):
    """Download a remote URL into dest (async)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as resp:
                if resp.status != 200:
                    print("Download failed with status:", resp.status)
                    return False
                data = await resp.read()
                dest.write_bytes(data)
                return True
    except Exception as e:
        print("Download exception:", e)
        return False

async def generate_murf_audio(text: str, voice_id: str = "en-IN-aarav"):
    """
    Call Murf TTS API to generate audio.
    Returns an audio URL (external) or saved local file path (string), or None on failure.
    """
    if not MURF_API_KEY:
        print("Warning: Murf API key missing")
        return None

    url = "https://api.murf.ai/v1/speech/generate"
    headers = {
        "accept": "application/json",
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "voice_id": voice_id,
        "output_format": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=120) as resp:
                if resp.status != 200:
                    print("Murf API returned status:", resp.status)
                    return None

                data = await resp.json()
                audio_url = data.get("audioFile") or data.get("audio_file") or data.get("audio_url") or data.get("audioFileUrl")

                if audio_url:
                    try:
                        # Download locally for stable serving
                        local_name = f"murf_{int(time.time())}_{uuid.uuid4().hex[:8]}.mp3"
                        local_path = STATIC_DIR / local_name
                        if await download_url_to_file(audio_url, local_path):
                            return f"/static/{local_name}"
                    except Exception as e:
                        print("Warning: Could not download Murf audio locally:", e)

                    # fallback to remote URL
                    return audio_url

                print("Warning: Murf response missing audio URL")
                return None

    except Exception as e:
        print("Murf TTS error:", e)
        return None
