from google import genai
from google.genai import types
import logging, requests, re
from dotenv import load_dotenv
from config import user_config

load_dotenv()
logger = logging.getLogger(__name__)

# 🎭 Persona configuration
DEFAULT_PERSONA = (
    "You are a friendly helpful assistant with a calm tone, "
    "speaking like a supportive teacher. "
    "Keep answers clear and not too long."
    "Call functions directly without asking for permission."
)

# --- Gemini client factory ---
def get_gemini_client():
    key = user_config.get("GEMINI_API_KEY")
    if not key:
        logger.error("❌ GEMINI_API_KEY missing (set via UI or .env)")
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as e:
        logger.error(f"❌ Could not initialize Gemini client: {e}")
        return None


# --- Gemini Response ---
async def get_gemini_response(user_input: str, persona: str = DEFAULT_PERSONA) -> str:
    client = get_gemini_client()
    if not client:
        return "[LLM unavailable – Gemini API key missing]"

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[{
                "role": "user",
                "parts": [{"text": f"{persona}\n\nNow respond to this message:\n{user_input}"}]
            }],
            config=config
        )

        # 🔍 Handle function calls
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if getattr(part, "function_call", None):
                    fn = part.function_call
                    if fn.name == "get_current_temperature":
                        return get_weather_with_advice(fn.args.get("location", "unknown"))
                    elif fn.name == "get_latest_news":
                        return get_latest_news(fn.args.get("topic", "general"), fn.args.get("country", "us"))
                    elif fn.name == "web_search":
                        return web_search(fn.args.get("query", ""), fn.args.get("max_results", 3))
                    elif fn.name == "generate_code":
                        return generate_code(fn.args.get("language", "Python"), fn.args.get("task", "print Hello World"))

        # --- Fallback: Gemini suggests a tool in text
        txt = getattr(response, "text", "")
        if txt and "web_search" in txt.lower():
            logger.info(f"Gemini suggested web_search → auto-running with query='{user_input}'")
            return web_search(user_input, 3)

        return txt or str(response)

    except Exception as e:
        logger.exception("Gemini LLM error")
        return f"[LLM error: {e}]"


# --- Function Declarations for Gemini ---
weather_function = {
    "name": "get_current_temperature",
    "description": "Gets the current temperature for a given location.",
    "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
}

news_function = {
    "name": "get_latest_news",
    "description": "Gets the latest news headlines.",
    "parameters": {
        "type": "object",
        "properties": {"topic": {"type": "string"}, "country": {"type": "string"}},
        "required": ["topic"],
    },
}

search_function = {
    "name": "web_search",
    "description": "Search the web using Tavily API.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}},
        "required": ["query"],
    },
}

code_function = {
    "name": "generate_code",
    "description": "Generate example code in a specified language.",
    "parameters": {
        "type": "object",
        "properties": {"language": {"type": "string"}, "task": {"type": "string"}},
        "required": ["language", "task"],
    },
}

tools = types.Tool(function_declarations=[weather_function, news_function, search_function, code_function])
config = types.GenerateContentConfig(tools=[tools])


# --- Weather ---
def get_weather_with_advice(location: str) -> str:
    api_key = user_config.get("OPENWEATHER_API_KEY")
    if not api_key:
        return "OpenWeather API key missing."

    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
    except Exception as e:
        return f"[Weather API error: {e}]"

    if "main" not in data:
        return f"Couldn't fetch weather for {location}. ({data})"

    temp, desc, main_weather = data["main"]["temp"], data["weather"][0]["description"], data["weather"][0]["main"]

    prompt = f"The current weather in {location} is {temp}°C with {desc} ({main_weather}). Give short, practical advice."
    client = get_gemini_client()
    if not client:
        return f"The current temperature in {location} is {temp}°C with {desc}. [Advice unavailable]"

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        advice = response.candidates[0].content.parts[0].text
    except Exception as e:
        advice = f"[Advice unavailable: {e}]"

    return f"The current temperature in {location} is {temp}°C with {desc}. {advice}"


# --- News ---
def get_latest_news(topic: str, country: str = "in") -> str:
    api_key = user_config.get("NEWS_API_KEY")
    if not api_key:
        return "News API key missing."

    valid_categories = ["business", "entertainment", "general", "health", "science", "sports", "technology"]
    if topic.lower() in valid_categories:
        url = f"https://newsapi.org/v2/top-headlines?country={country}&category={topic}&apiKey={api_key}"
    else:
        url = f"https://newsapi.org/v2/everything?q={topic}&language=en&sortBy=publishedAt&apiKey={api_key}"

    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if "articles" in data and data["articles"]:
            headlines = [a["title"] for a in data["articles"][:5] if a.get("title")]
            return "📰 Top headlines:\n- " + "\n- ".join(headlines)
        return f"Couldn't fetch news. ({data.get('message','no articles found')})"
    except Exception as e:
        logger.exception("News API failed")
        return f"[News API error: {e}]"


# --- Web Search ---
def web_search(query: str, max_results: int = 3) -> str:
    api_key = user_config.get("TAVILY_API_KEY")
    if not api_key:
        return "Tavily API key missing."

    url, headers = "https://api.tavily.com/search", {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, headers=headers, json={"query": query, "num_results": max_results}, timeout=8)
        data = resp.json()
        if "results" in data:
            results = data["results"][:max_results]
            formatted = []
            for r in results:
                snippet = r.get("snippet") or r.get("content")
                if snippet:
                    formatted.append(f"{snippet} (source: {r['url']})")
                else:
                    formatted.append(f"{r.get('title','[No title]')} - {r.get('url','')}")
            return "🔎 Search results:\n- " + "\n- ".join(formatted)
        return f"No results found. ({data})"
    except Exception as e:
        logger.exception("Tavily API failed")
        return f"[Search API error: {e}]"


# --- Code Generation ---
def clean_code_output(text: str) -> str:
    code_blocks = re.findall(r"```(?:[a-zA-Z0-9]+)?\n([\s\S]*?)```", text)
    if code_blocks:
        return code_blocks[0].strip()
    lines = text.splitlines()
    code_lines = [ln for ln in lines if not ln.strip().startswith(("*", "-", "#", "Explanation", "**"))]
    return "\n".join(code_lines).strip()


def generate_code(language: str, task: str) -> str:
    try:
        prompt = f"Write {language} code to {task}. Return ONLY the code, no explanations."
        client = get_gemini_client()
        if not client:
            return "[Code generation unavailable – Gemini key missing]"
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=[{"role": "user", "parts": [{"text": prompt}]}])
        return clean_code_output(resp.text or "")
    except Exception as e:
        logger.exception("Code generation failed")
        return f"[Code generation error: {e}]"
