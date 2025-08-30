# 🎙️ AI Voice Agent: Jarvis

A conversational AI agent that lets you talk naturally with your browser.  
It records your voice, transcribes it with **AssemblyAI**, and replies with lifelike speech from **Murf API** — all powered by **FastAPI** and **Google Gemini** for intelligent responses.  

Now fully deployed and accessible online via **Render** 🚀.

---

## ✨ What's New
- **🔑 Dynamic API Key Setup** – Enter your own API keys directly from the UI (no need to modify `.env`).
- **☁️ Cloud Deployment** – Hosted publicly on [Render](https://render.com), making it accessible from anywhere.
- **💬 Seamless Voice Conversations** – Real-time speech-to-text and text-to-speech integration.
- **🎛️ Configurable UI** – Simple dialog for API key setup and clean recording interface.
- **⚡ End-to-End Automation** – Voice in → Transcription → AI Response → Voice out, all in one click.

---

## 🚀 Features
- 🎤 **Real-time Voice Recording** – Start and stop recording from the browser.  
- 📝 **Speech-to-Text (AssemblyAI)** – Accurate audio transcription.  
- 🗣️ **Text-to-Speech (Murf API)** – Natural AI-generated voice responses.  
- 🤖 **AI Conversation (Google Gemini)** – Smart, contextual replies.  
- 🖥️ **Interactive Frontend** – Responsive design with animated record button.  
- 🌍 **Public Hosting** – Accessible online via HTTPS + secure WebSocket (WSS).  

---

## 🛠 Tech Stack
- **Backend:** FastAPI (Python)  
- **Frontend:** HTML, CSS, JavaScript  
- **Speech-to-Text:** AssemblyAI API  
- **Text-to-Speech:** Murf API  
- **AI Processing:** Google Gemini API  
- **Server:** Uvicorn  
- **Deployment:** Render (Free Tier)  
- **Environment Management:** python-dotenv  

---

## 📦 Installation (Local Development)

```bash
git clone -b streaming https://github.com/<your-username>/AIVoiceAgent.git
cd AIVoiceAgent

# Create and activate a virtual environment
python -m venv venv  
venv\Scripts\activate  # On Windows

# Or Mac/Linux
python3 -m venv venv  
source venv/bin/activate  

# Install dependencies
pip install -r requirements.txt

# Create a .env file in the project root:
# ASSEMBLYAI_API_KEY=your_assemblyai_api_key
# MURF_API_KEY=your_murf_api_key
# GEMINI_API_KEY=your_gemini_api_key

# Run locally
uvicorn main:app --reload

---


30-days-voice-agents/
│── main.py
│── .env
│── requirements.txt
│
├── static/
│   ├── script.js
│   └── style.css
│
├── uploads/
│
├── templates/
│   └── index.html
│
├── services/
│   ├── __init__.py
│   ├── tts_service.py
│   ├── stt_service.py
│   └── llm_service.py
│
└── README.md

---
🌐 Live Demo
👉 Try it here
---
📌 Next Steps

✅ Improve conversation memory
✅ Add support for multiple TTS voices


🤝 Contributing

Pull requests are welcome! Feel free to open issues for new features or bug fixes.


---

👉 After saving, open the **Markdown preview in VS Code** (`Ctrl + Shift + V`) to check how it looks.  

Do you want me to give you a **minimal copy-paste version** (no explanations, only final text) so you can drop it directly into `README.md`?
