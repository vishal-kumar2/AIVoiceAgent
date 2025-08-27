#llm_service.py
from google import genai
from google.genai import types
import os, logging
import requests
from dotenv import load_dotenv

load_dotenv()

print("🔑 GEMINI_API_KEY =", os.getenv("GEMINI_API_KEY"))
print("🔑 OPENWEATHER_API_KEY =", os.getenv("OPENWEATHER_API_KEY"))
logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

client = None
if genai and GEMINI_KEY:
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        logger.info("✅ Gemini client initialized")
    except Exception as e:
        logger.error("❌ Could not initialize Gemini client: %s", e)
else:
    if not genai:
        logger.error("❌ google.genai package not installed")
    if not GEMINI_KEY:
        logger.error("❌ GEMINI_API_KEY not set")


# 🎭 Persona configuration
DEFAULT_PERSONA = (
    "You are a friendly helpful assistant with a calm tone, "
    "speaking like a supportive teacher. "
    "Keep answers clear and not too long."
    
    "call the function directly without asking for permission."
)

async def get_gemini_response(user_input: str, persona: str = DEFAULT_PERSONA) -> str:
    """
    Returns Gemini response with persona injected.
    """
    if not client:
        return "[LLM unavailable]"

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": f"{persona}\n\nNow respond to this message:\n{user_input}"}
                    ]
                }
            ],
            config=config 
        )

        # 🔍 Check if Gemini asked to call a function
                # 🔍 Check if Gemini asked to call a function
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if getattr(part, "function_call", None):
                    fn = part.function_call
                    if fn.name == "get_current_temperature":
                        location = fn.args.get("location", "unknown")
                        return get_weather_with_advice(location)
                    elif fn.name == "get_latest_news":
                        topic = fn.args.get("topic", "general")
                        country = fn.args.get("country", "us")
                        return get_latest_news(topic, country)
                    elif fn.name == "web_search":
                        query = fn.args.get("query", "")
                        max_results = fn.args.get("max_results", 3)
                        return web_search(query, max_results)
                    elif fn.name == "generate_code":
                        lang = fn.args.get("language", "Python")
                        task = fn.args.get("task", "print Hello World")
                        return generate_code(lang, task)


        # --- Fallback: if Gemini just suggests a tool instead of calling it
        txt = getattr(response, "text", "")
        if txt and "web_search" in txt.lower():
            logger.info(f"Gemini suggested web_search → auto-running with query='{user_input}'")
            return web_search(user_input, 3)

        return txt or str(response)

    except Exception as e:
        logger.exception("Gemini LLM error")
        return f"[LLM error: {e}]"

       


weather_function = {
    "name": "get_current_temperature",
    "description": "Gets the current temperature for a given location.",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name, e.g. London",
            },
        },
        "required": ["location"],
    },
}

# --- News Function ---
news_function = {
    "name": "get_latest_news",
    "description": "Gets the latest news headlines for a given topic or country.",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic keyword (e.g., technology, sports, politics)",
            },
            "country": {
                "type": "string",
                "description": "Country code (e.g., 'us', 'in')",
            },
        },
        "required": ["topic"],
    },
}

# --- Search Function ---
search_function = {
    "name": "web_search",
    "description": "Search the web using Tavily API and return top results.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query text, e.g. 'latest AI trends'",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default 3)",
            },
        },
        "required": ["query"],
    },
}

{
    "name": "generate_code",
    "description": "Generate example code in a specified programming language for a given task.",
    "parameters": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "Programming language, e.g., Python, JavaScript, Java"
            },
            "task": {
                "type": "string",
                "description": "The task or problem to solve, e.g., 'reverse a string'"
            }
        },
        "required": ["language", "task"]
    },
}




tools = types.Tool(function_declarations=[weather_function,news_function,search_function])
config = types.GenerateContentConfig(tools=[tools])

# --- Real weather fetcher (OpenWeather API as example) ---
# --- Real weather fetcher (OpenWeather API as example) ---


def get_weather_with_advice(location: str) -> str:
    api_key = os.getenv("OPENWEATHER_API_KEY")
    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    resp = requests.get(url, timeout=5)
    data = resp.json()

    if "main" not in data:
        return f"Couldn't fetch weather for {location}. ({data})"

    temp = data["main"]["temp"]
    desc = data["weather"][0]["description"]
    main_weather = data["weather"][0]["main"]

    # 🎯 Pass weather data to LLM for dynamic advice
    prompt = f"""
    The current weather in {location} is {temp}°C with {desc} ({main_weather}).
    Based on this, give practical advice for someone in {location}.
    Example: carry umbrella, stay hydrated, wear warm clothes, avoid driving etc.
    Keep it short and helpful.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        advice = response.candidates[0].content.parts[0].text
    except Exception as e:
        advice = f"[Advice unavailable: {e}]"

    return f"The current temperature in {location} is {temp}°C with {desc}. {advice}"

# --- Real news fetcher (using NewsAPI as example) ---
def get_latest_news(topic: str, country: str = "in") -> str:
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return "News API key missing."

    # if topic is one of NewsAPI categories, use top-headlines with category
    valid_categories = ["business", "entertainment", "general", "health", "science", "sports", "technology"]
    if topic.lower() in valid_categories:
        url = f"https://newsapi.org/v2/top-headlines?country={country}&category={topic}&apiKey={api_key}"
    else:
        # fallback to everything endpoint
        url = f"https://newsapi.org/v2/everything?q={topic}&language=en&sortBy=publishedAt&apiKey={api_key}"

    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if "articles" in data and data["articles"]:
            headlines = [a["title"] for a in data["articles"][:5] if a.get("title")]
            return "Here are the top news headlines:\n- " + "\n- ".join(headlines)
        return f"Couldn't fetch news. ({data.get('message','no articles found')})"
    except Exception as e:
        logger.exception("News API failed")
        return f"[News API error: {e}]"
    

def web_search(query: str, max_results: int = 3) -> str:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Tavily API key missing."

    url = "https://api.tavily.com/search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"query": query, "num_results": max_results}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=8)
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

            return "📌 Here's what I found:\n- " + "\n- ".join(formatted)
        return f"No results found. ({data})"
    except Exception as e:
        logger.exception("Tavily API failed")
        return f"[Search API error: {e}]"
    

    

# --- Clean Code Output Helper ---
import re

def clean_code_output(text: str) -> str:
    """
    Extract ONLY code from Gemini output.
    - Removes explanations, markdown, extra sentences.
    """
    # Capture content inside triple backticks first
    code_blocks = re.findall(r"```(?:[a-zA-Z0-9]+)?\n([\s\S]*?)```", text)
    if code_blocks:
        return code_blocks[0].strip()

    # If no fenced block, strip out everything except code-like lines
    lines = text.splitlines()
    code_lines = [ln for ln in lines if not ln.strip().startswith(("*", "-", "#", "Explanation", "**"))]
    return "\n".join(code_lines).strip()


def generate_code(language: str, task: str) -> str:
    """
    Generate code in a given language for a given task.
    Ensures output is ONLY code (no explanations).
    """
    try:
        prompt = (
            f"Write {language} code to {task}. "
            f"Return ONLY the code. Do NOT add explanations, text, or markdown fences."
        )

        resp = genai.GenerativeModel("gemini-1.5-flash").generate_content(prompt)

        if not resp.text:
            return "⚠️ Could not generate code."

        return clean_code_output(resp.text)

    except Exception as e:
        logger.exception("Code generation failed")
        return f"[Code generation error: {e}]"
