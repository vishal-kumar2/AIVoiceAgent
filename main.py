# main.py
import os
import shutil
import uuid
import asyncio
import aiohttp
import time
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Optional Gemini client
try:
    from google import genai
except Exception:
    genai = None

load_dotenv()

# App + directories
app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# API keys
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")

# optional init of Gemini client
if genai and GEMINI_KEY:
    try:
        client = genai.Client(api_key=GEMINI_KEY)
    except Exception as e:
        print("Warning: Could not initialize Gemini client:", e)
        client = None
else:
    client = None
    if not genai:
        print("Warning: google.genai package not available; /llm/query will fail if used.")
    if not GEMINI_KEY:
        print("Warning: GEMINI_API_KEY not set; /llm/query will fail if used.")

# in-memory chat store (for quick prototyping)
chat_history_store = {}

# fallback audio file inside static/
FALLBACK_AUDIO_FILE = STATIC_DIR / "fallback_audio.mp3"
FALLBACK_TEXT = "I'm having trouble connecting right now. Please try again later."

# === Utilities ===

async def download_url_to_file(url: str, dest: Path):
    """Download a remote URL into dest (async)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as resp:
                if resp.status != 200:
                    print("Download failed:", resp.status)
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
        print("Murf API key missing")
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
        # Some Murf APIs expect extra params; we request JSON response
        "output_format": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=120) as resp:
                text_body = await resp.text()
                print("Murf API response:", resp.status, text_body)
                if resp.status != 200:
                    return None
                data = await resp.json()
                # Murf may return audioFile or audio_file or audio_url; check variants
                audio_url = data.get("audioFile") or data.get("audio_file") or data.get("audio_url") or data.get("audioFileUrl")
                if audio_url:
                    # Option: download into static folder to serve locally, for stability
                    try:
                        local_name = f"murf_{int(time.time())}_{uuid.uuid4().hex[:8]}.mp3"
                        local_path = STATIC_DIR / local_name
                        ok = await download_url_to_file(audio_url, local_path)
                        if ok:
                            return f"/static/{local_name}"
                        # if download failed, return remote url
                    except Exception as e:
                        print("Could not download Murf audio:", e)
                    return audio_url
                return None
    except Exception as e:
        print("Murf TTS error:", e)
        return None

async def transcribe_with_assemblyai(filepath: str):
    """
    Upload file to AssemblyAI and transcribe. Returns transcript text or None on failure.
    """
    if not ASSEMBLYAI_API_KEY:
        print("AssemblyAI key missing")
        return None

    upload_url = "https://api.assemblyai.com/v2/upload"
    headers = {"authorization": ASSEMBLYAI_API_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            # upload file (binary)
            with open(filepath, "rb") as f:
                async with session.post(upload_url, headers=headers, data=f, timeout=120) as up_res:
                    if up_res.status not in (200, 201):
                        print("AssemblyAI upload failed status:", up_res.status)
                        return None
                    up_json = await up_res.json()
                    audio_url = up_json.get("upload_url")
                    if not audio_url:
                        print("AssemblyAI upload missing upload_url")
                        return None

            # request a transcription
            transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
            payload = {"audio_url": audio_url}
            async with session.post(transcript_endpoint, headers=headers, json=payload, timeout=60) as t_res:
                if t_res.status not in (200, 201):
                    print("AssemblyAI transcript start failed:", t_res.status)
                    return None
                t_json = await t_res.json()
                transcript_id = t_json.get("id")
                if not transcript_id:
                    print("AssemblyAI transcript missing id")
                    return None

            # poll
            polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
            for _ in range(60):  # up to ~2 minutes (with sleep)
                async with session.get(polling_url, headers=headers, timeout=30) as p_res:
                    if p_res.status != 200:
                        print("AssemblyAI poll error:", p_res.status)
                        await asyncio.sleep(1.5)
                        continue
                    p_json = await p_res.json()
                    status = p_json.get("status")
                    if status == "completed":
                        return p_json.get("text")
                    if status == "error":
                        print("AssemblyAI reported error:", p_json.get("error"))
                        return None
                await asyncio.sleep(2)
            print("AssemblyAI transcription timed out")
            return None
    except Exception as e:
        print("AssemblyAI exception:", e)
        return None

# Ensure fallback audio exists: prefer generating it via Murf if possible
async def ensure_fallback_audio():
    if FALLBACK_AUDIO_FILE.exists():
        return
    if MURF_API_KEY:
        print("Generating fallback audio using Murf...")
        audio_url = await generate_murf_audio(FALLBACK_TEXT, voice_id="en-IN-aarav")
        if audio_url:
            # If generate_murf_audio downloaded locally it returns /static/..., else remote url.
            # If remote, try to download it locally
            if audio_url.startswith("/static/"):
                # already local (generated & downloaded earlier)
                print("Fallback audio created at", audio_url)
                return
            # else try to download remote
            ok = await download_url_to_file(audio_url, FALLBACK_AUDIO_FILE)
            if ok:
                print("Fallback audio downloaded to", FALLBACK_AUDIO_FILE)
                return
    print("Fallback audio not available. Please add a file at:", FALLBACK_AUDIO_FILE)

# schedule ensure at startup
@app.on_event("startup")
async def startup_event():
    await ensure_fallback_audio()

# === Models ===
class TTSRequest(BaseModel):
    text: str
    voice_id: str | None = None

class LLMQuery(BaseModel):
    text: str

# === Routes ===

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    # serve templates/index.html — ensure exists in templates folder
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate-audio")
async def generate_audio_endpoint(req: TTSRequest):
    try:
        voice = req.voice_id or "en-IN-aarav"
        audio_url = await generate_murf_audio(req.text, voice_id=voice)
        if not audio_url:
            # fallback
            if FALLBACK_AUDIO_FILE.exists():
                return {"audio_url": f"/static/{FALLBACK_AUDIO_FILE.name}"}
            return JSONResponse({"detail": "TTS failed"}, status_code=500)
        return {"audio_url": audio_url}
    except Exception as e:
        print("generate-audio error:", e)
        if FALLBACK_AUDIO_FILE.exists():
            return {"audio_url": f"/static/{FALLBACK_AUDIO_FILE.name}"}
        return JSONResponse({"detail": "Server error"}, status_code=500)

@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, audio_file: UploadFile = File(...)):
    """
    Accepts uploaded audio file, transcribes with AssemblyAI, sends transcript to Gemini LLM,
    gets LLM reply, converts reply to Murf TTS and returns audio_url + transcription + session_id.
    Robust error handling and fallback audio provided.
    """
    try:
        # save incoming file
        incoming_name = f"{uuid.uuid4().hex}_{audio_file.filename}"
        saved_path = UPLOAD_DIR / incoming_name
        with open(saved_path, "wb") as out_f:
            shutil.copyfileobj(audio_file.file, out_f)
        print("Saved file to:", saved_path)

        # STT
        transcript = await transcribe_with_assemblyai(str(saved_path))
        if not transcript:
            print("STT failed or returned empty")
            # return fallback audio and indicate error
            if FALLBACK_AUDIO_FILE.exists():
                return {
                    "session_id": session_id or None,
                    "transcription": None,
                    "llm_text": None,
                    "audio_url": f"/static/{FALLBACK_AUDIO_FILE.name}",
                    "error": "STT failed"
                }
            return JSONResponse({"detail": "STT failed"}, status_code=500)




        # session management: simple in-memory
        if not session_id:
            session_id = str(uuid.uuid4())
            chat_history_store[session_id] = []
        if session_id not in chat_history_store:
            chat_history_store[session_id] = []

        # append user message
        chat_history_store[session_id].append({"role": "user", "content": transcript})

        # build prompt with history
        history_parts = []
        for msg in chat_history_store[session_id]:
            role = msg.get("role", "user").capitalize()
            history_parts.append(f"{role}: {msg.get('content')}")
        history_str = "\n".join(history_parts)
        prompt = (
            "You are a helpful assistant that always replies in English.\n"
            "Continue the conversation naturally.\n\n"
            f"{history_str}\nAssistant:"
        )

        # LLM
        llm_text = None
        if client and GEMINI_KEY:
            try:
                gen_response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                llm_text = getattr(gen_response, "text", str(gen_response))
            except Exception as e:
                print("LLM (Gemini) error:", e)
                llm_text = None
        else:
            print("Gemini client not configured; returning fallback reply text")
            llm_text = None

        if not llm_text:
            # fallback LLM reply text
            fallback_reply = "I'm having trouble connecting to the language model right now."
            llm_text = fallback_reply

        # store assistant reply
        chat_history_store[session_id].append({"role": "assistant", "content": llm_text})

        # TTS (Murf)
        audio_url = await generate_murf_audio(llm_text)
        if not audio_url:
            # fallback
            if FALLBACK_AUDIO_FILE.exists():
                audio_url = f"/static/{FALLBACK_AUDIO_FILE.name}"
            else:
                audio_url = None

        response_payload = {
            "session_id": session_id,
            "transcription": transcript,
            "llm_text": llm_text,
            "audio_url": audio_url,
            "history": chat_history_store[session_id]
        }
        return response_payload

    except Exception as e:
        print("tts/echo unexpected error:", e)
        if FALLBACK_AUDIO_FILE.exists():
            return {
                "session_id": session_id or None,
                "transcription": None,
                "llm_text": None,
                "audio_url": f"/static/{FALLBACK_AUDIO_FILE.name}",
                "error": "Unexpected server error"
            }
        return JSONResponse({"detail": "Unexpected server error"}, status_code=500)

@app.post("/llm/query")
async def llm_query_endpoint(body: LLMQuery):
    try:
        if not client or not GEMINI_KEY:
            return JSONResponse({"error": "LLM not configured"}, status_code=500)
        gen_response = client.models.generate_content(model="gemini-2.5-flash", contents=body.text)
        return {"response": getattr(gen_response, "text", str(gen_response))}
    except Exception as e:
        print("/llm/query error:", e)
        return JSONResponse({"error": "LLM call failed"}, status_code=500)

# quick endpoint to view chat history (debug)
@app.get("/chat/history/{session_id}")
def get_history(session_id: str):
    return {"session_id": session_id, "history": chat_history_store.get(session_id, [])}
