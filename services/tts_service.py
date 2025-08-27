import os
import aiohttp
import base64
import logging

logger = logging.getLogger(__name__)
MURF_API_KEY = os.getenv("MURF_API_KEY")
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"
VOICE_ID = "en-IN-aarav"

HEADERS = {
    "api-key": MURF_API_KEY,
    "Content-Type": "application/json"
}

async def murf_tts_base64(text: str, voice_id: str = VOICE_ID) -> str:
    """
    Get Murf TTS as full base64-encoded MP3, with dynamic voice support.
    """
    payload = {
        "voiceId": voice_id,
        "text": text,
        "format": "mp3",
        "sampleRate": 16000,
        "channelType": "stereo",
        "responseFormat": "json"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(MURF_API_URL, headers=HEADERS, json=payload) as resp:
                if resp.status != 200:
                    logger.error("Murf API error: %s", await resp.text())
                    return None
                data = await resp.json()
                audio_url = data.get("audioFile")
                if not audio_url:
                    logger.error("No audioFile in Murf response: %s", data)
                    return None

            async with session.get(audio_url) as audio_resp:
                if audio_resp.status != 200:
                    logger.error("Failed to fetch audio: %s", await audio_resp.text())
                    return None
                audio_bytes = await audio_resp.read()
                return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        logger.exception("Error fetching Murf TTS: %s", e)
        return None
