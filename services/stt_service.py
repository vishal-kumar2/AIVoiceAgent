import asyncio
import aiohttp
from config import user_config   # 🔑 pull config from main.py

async def transcribe_with_assemblyai(filepath: str):
    """
    Upload file to AssemblyAI and transcribe. Returns transcript text or None on failure.
    """
    api_key = user_config.get("ASSEMBLYAI_API_KEY")   # 👈 dynamic lookup
    if not api_key:
        print("❌ AssemblyAI API key missing (set it via UI)")
        return None

    upload_url = "https://api.assemblyai.com/v2/upload"
    headers = {"authorization": api_key}
    try:
        async with aiohttp.ClientSession() as session:
            # --- Upload audio file ---
            with open(filepath, "rb") as f:
                async with session.post(upload_url, headers=headers, data=f, timeout=120) as up_res:
                    if up_res.status not in (200, 201):
                        print("❌ AssemblyAI upload failed:", up_res.status)
                        return None
                    up_json = await up_res.json()
                    audio_url = up_json.get("upload_url")
                    if not audio_url:
                        print("❌ AssemblyAI response missing upload_url")
                        return None

            # --- Start transcription ---
            transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
            payload = {"audio_url": audio_url}
            async with session.post(transcript_endpoint, headers=headers, json=payload, timeout=60) as t_res:
                if t_res.status not in (200, 201):
                    print("❌ AssemblyAI transcript request failed:", t_res.status)
                    return None
                t_json = await t_res.json()
                transcript_id = t_json.get("id")
                if not transcript_id:
                    print("❌ AssemblyAI transcript response missing id")
                    return None

            # --- Poll until completion ---
            polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
            for _ in range(60):  # up to ~2 minutes
                async with session.get(polling_url, headers=headers, timeout=30) as p_res:
                    if p_res.status != 200:
                        print("⚠️ Polling error:", p_res.status)
                        await asyncio.sleep(1.5)
                        continue
                    p_json = await p_res.json()
                    status = p_json.get("status")
                    if status == "completed":
                        return p_json.get("text")
                    if status == "error":
                        print("❌ AssemblyAI error:", p_json.get("error"))
                        return None
                await asyncio.sleep(2)

            print("⌛ AssemblyAI transcription timed out")
            return None

    except Exception as e:
        print("❌ AssemblyAI exception:", e)
        return None
