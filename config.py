import os
# --- Dynamic user API key config ---
user_config = {
    "ASSEMBLYAI_API_KEY": os.getenv("ASSEMBLYAI_API_KEY"),
    "MURF_API_KEY": os.getenv("MURF_API_KEY"),
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    "OPENWEATHER_API_KEY": os.getenv("OPENWEATHER_API_KEY"),
    "NEWS_API_KEY": os.getenv("NEWS_API_KEY"),
    "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
}