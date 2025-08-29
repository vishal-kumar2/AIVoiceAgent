# services/tts_service.py
import os, aiohttp, base64, logging
logger = logging.getLogger(__name__)
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"

async def murf_tts_base64(text: str, voice_id: str, murf_api_key: str) -> str:
    """
    Get Murf TTS as base64 MP3. Uses provided API key dynamically.
    """
    if not murf_api_key:
        logger.error("MURF_API_KEY missing")
        return None

    headers = {
        "api-key": murf_api_key,
        "Content-Type": "application/json"
    }

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
            async with session.post(MURF_API_URL, headers=headers, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    logger.error("Murf API error: %s", await resp.text())
                    return None
                data = await resp.json()
                audio_url = data.get("audioFile")
                if not audio_url:
                    logger.error("No audioFile in Murf response: %s", data)
                    return None

            async with session.get(audio_url, timeout=60) as audio_resp:
                if audio_resp.status != 200:
                    logger.error("Failed to fetch audio: %s", await audio_resp.text())
                    return None
                audio_bytes = await audio_resp.read()
                return base64.b64encode(audio_bytes).decode("utf-8")

    except Exception as e:
        logger.exception("Error fetching Murf TTS: %s", e)
        return None
