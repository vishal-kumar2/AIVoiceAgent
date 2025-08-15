from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
import shutil
import uuid
import os
from dotenv import load_dotenv

# --- Load .env before importing any services ---
BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR / ".env"
if not dotenv_path.exists():
    raise FileNotFoundError(f".env not found at {dotenv_path}")
load_dotenv(dotenv_path)

'''print("GEMINI_API_KEY =", os.getenv("GEMINI_API_KEY"))
print("ASSEMBLYAI_API_KEY =", os.getenv("ASSEMBLYAI_API_KEY"))
print("MURF_API_KEY =", os.getenv("MURF_API_KEY"))'''

# --- Now import services ---
from services.tts_service import generate_murf_audio, download_url_to_file
from services.stt_service import transcribe_with_assemblyai
from services.llm_service import query_gemini

app = FastAPI()

UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
for d in [UPLOAD_DIR, STATIC_DIR, TEMPLATES_DIR]:
    d.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

FALLBACK_AUDIO_FILE = STATIC_DIR / "fallback_audio.mp3"
FALLBACK_TEXT = "I'm having trouble connecting right now. Please try again later."
chat_history_store = {}

async def ensure_fallback_audio():
    if not FALLBACK_AUDIO_FILE.exists():
        audio_url = await generate_murf_audio(FALLBACK_TEXT, voice_id="en-IN-aarav")
        if audio_url and not audio_url.startswith("/static/"):
            await download_url_to_file(audio_url, FALLBACK_AUDIO_FILE)

@app.on_event("startup")
async def startup_event():
    await ensure_fallback_audio()

class TTSRequest(BaseModel):
    text: str
    voice_id: str | None = None

class LLMQuery(BaseModel):
    text: str

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate-audio")
async def generate_audio_endpoint(req: TTSRequest):
    voice = req.voice_id or "en-IN-aarav"
    audio_url = await generate_murf_audio(req.text, voice_id=voice)
    if not audio_url:
        if FALLBACK_AUDIO_FILE.exists():
            return {"audio_url": f"/static/{FALLBACK_AUDIO_FILE.name}"}
        return JSONResponse({"detail": "TTS failed"}, status_code=500)
    return {"audio_url": audio_url}

@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, audio_file: UploadFile = File(...)):
    incoming_name = f"{uuid.uuid4().hex}_{audio_file.filename}"
    saved_path = UPLOAD_DIR / incoming_name
    with open(saved_path, "wb") as out_f:
        shutil.copyfileobj(audio_file.file, out_f)

    transcript = await transcribe_with_assemblyai(str(saved_path))
    if not transcript:
        return {
            "session_id": session_id,
            "transcription": None,
            "llm_text": None,
            "audio_url": f"/static/{FALLBACK_AUDIO_FILE.name}",
            "error": "STT failed"
        }

    chat_history_store.setdefault(session_id, []).append({"role": "user", "content": transcript})

    history_text = "\n".join(f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history_store[session_id])
    prompt = (
        "You are a helpful assistant that always replies in English.\n"
        "Continue the conversation naturally.\n\n"
        f"{history_text}\nAssistant:"
    )

    llm_text = query_gemini(prompt) or "I'm having trouble connecting to the language model right now."
    chat_history_store[session_id].append({"role": "assistant", "content": llm_text})

    audio_url = await generate_murf_audio(llm_text) or f"/static/{FALLBACK_AUDIO_FILE.name}"

    return {
        "session_id": session_id,
        "transcription": transcript,
        "llm_text": llm_text,
        "audio_url": audio_url,
        "history": chat_history_store[session_id]
    }

@app.post("/llm/query")
async def llm_query_endpoint(body: LLMQuery):
    llm_response = query_gemini(body.text)
    if llm_response is None:
        return JSONResponse({"error": "LLM call failed"}, status_code=500)
    return {"response": llm_response}

@app.get("/chat/history/{session_id}")
def get_history(session_id: str):
    return {"session_id": session_id, "history": chat_history_store.get(session_id, [])}
