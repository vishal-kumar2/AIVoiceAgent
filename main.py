# main.py
import os
import asyncio
import logging
import threading
from pathlib import Path
import base64

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from fastapi import  Request
from config import user_config

from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions,
    StreamingParameters, StreamingEvents,
    BeginEvent, TurnEvent, TerminationEvent,
    StreamingError
)

load_dotenv()
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")






# Import helper functions
from services.llm_service import get_gemini_response
from services.tts_service import murf_tts_base64  # async generator yielding base64 chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

from fastapi import Body

@app.post("/config/update")
async def update_config(data: dict = Body(...)):
    """
    Update API keys dynamically from UI.
    Example JSON:
    {
        "MURF_API_KEY": "abc123",
        "ASSEMBLYAI_API_KEY": "xyz789"
    }
    """
    for key, val in data.items():
        if key in user_config and val:
            user_config[key] = val.strip()
            logger.info(f"🔑 Updated {key} via UI")
    return {"status": "ok", "config": {k: "****" if v else None for k,v in user_config.items()}}


@app.get("/config")
async def get_config():
    """
    Return current config (with masked values).
    """
    return {k: "****" if v else None for k, v in user_config.items()}

@app.get("/")
async def get_test():
    html_path = BASE_DIR / "templates" / "test.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# 🎭 Persona definitions (keep them at the top or outside the function)
persona_map = {
    "teacher": {
        "prompt": "You are a friendly helpful assistant with a calm tone. Explain concepts clearly.",
        "voice": "en-IN-aarav"   # calm, clear voice
    },
    "pirate": {
        "prompt": "You are a witty pirate. Always speak like a pirate from the Caribbean. Use 'Arrr', 'matey', 'booty'. Never break character.",
        "voice": "en-IN-aarav"   # rougher, deeper voice
    },
    "cowboy": {
        "prompt": "You are a cowboy from the Wild West. Use cowboy slang. Speak like you're around a campfire with your herd.",
        "voice": "en-IN-aarav"   # rustic, storytelling tone
    },
    "robot": {
        "prompt": "You are a robot with a mechanical tone. Be concise. Speak like a machine.",
        "voice": "en-US-daisy"    # robotic voice
    },
    "comedian": {  # ← New persona
        "prompt": "You are a stand-up comedian. Make witty jokes, puns, and funny remarks relevant to the conversation. Keep a cheerful, playful tone.",
        "voice": "en-IN-aarav"  # or another voice of your choice
    }
}


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_input = body.get("message", "")
    persona_choice = body.get("persona", "teacher")
    logger.info(f"🧑 Persona selected: {persona_choice}") 

    # ✅ pick persona safely
    persona = persona_map.get(persona_choice, persona_map["teacher"])
    reply = await get_gemini_response(user_input, persona["prompt"])

    return {"reply": reply}

logger.info("Default persona is teacher until client sends update...")

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("🎙️ WebSocket client connected")
    loop = asyncio.get_event_loop()

    # Default persona
    persona_choice = "teacher"
    persona = persona_map[persona_choice]

    client = StreamingClient(StreamingClientOptions(api_key=user_config["ASSEMBLYAI_API_KEY"]))


# in main.py
    conversation_history = []

    async def handle_turn(transcript: str):
        await websocket.send_text(f"USER:{transcript}")
        
        conversation_history.append({"role": "user", "content": transcript})
        llm_response = await get_gemini_response(conversation_history, persona["prompt"])
        conversation_history.append({"role": "assistant", "content": llm_response})

        await websocket.send_text(f"LLM:{llm_response}")
        audio_b64 = await murf_tts_base64(
            llm_response,
            persona["voice"],
            user_config["MURF_API_KEY"]   # ✅ dynamic API key
        )

        if audio_b64:
            await websocket.send_text(f"AUDIO:{audio_b64}")


    # AssemblyAI callbacks
    def on_begin(client_obj, event: BeginEvent):
        logger.info(f"AssemblyAI session started: {getattr(event, 'id', '')}")

    def on_turn(client_obj, event: TurnEvent):
        transcript = (event.transcript or "").strip()
        if event.end_of_turn and transcript:
            logger.info(f"✅ Final Turn Transcript: {transcript}")
            asyncio.run_coroutine_threadsafe(handle_turn(transcript), loop)

    def on_terminated(client_obj, event: TerminationEvent):
        logger.info(f"AssemblyAI session terminated: processed {getattr(event, 'audio_duration_seconds', None)} sec")

    def on_error(client_obj, error: StreamingError):
        logger.error("AssemblyAI streaming error: %s", error)

    client.on(StreamingEvents.Begin, on_begin)
    client.on(StreamingEvents.Turn, on_turn)
    client.on(StreamingEvents.Termination, on_terminated)
    client.on(StreamingEvents.Error, on_error)

    threading.Thread(target=lambda: client.connect(
        StreamingParameters(
            sample_rate=16000,
            enable_turn_detection=True,
            end_of_turn_silence_threshold=500
        )
    ), daemon=True).start()

    # --- WebSocket receive loop ---
    try:
        while True:
            try:
                msg = await websocket.receive()
            except WebSocketDisconnect:
                logger.info("🔌 Client disconnected")
                break  # exit the loop immediately

            # Persona switch
            if msg.get("text") is not None:
                text_msg = msg["text"]
                if text_msg.startswith("PERSONA:"):
                    persona_choice = text_msg.replace("PERSONA:", "").strip()
                    persona = persona_map.get(persona_choice, persona_map["teacher"])
                    logger.info(f"🧑 Persona switched to: {persona_choice}")

            # Audio stream
            elif msg.get("bytes") is not None:
                client.stream(msg["bytes"])

    finally:
        try:
            client.disconnect(terminate=True)
        except Exception:
            logger.exception("Error disconnecting AssemblyAI client")
        logger.info("🔒 Session closed")




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)