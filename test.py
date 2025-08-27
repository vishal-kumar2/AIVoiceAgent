import asyncio
from pathlib import Path
from services.tts_service import get_murf_tts_audio

async def test():
    audio_data = await get_murf_tts_audio("Hello, this is a Murf TTS debug test")
    out_path = Path("output.wav")
    out_path.write_bytes(audio_data)
    print(f"✅ Saved Murf TTS to {out_path}")

if __name__ == "__main__":
    asyncio.run(test())
