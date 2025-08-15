import os

try:
    from google import genai
except Exception:
    genai = None

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if genai and GEMINI_KEY:
    try:
        client = genai.Client(api_key=GEMINI_KEY)
    except Exception as e:
        print("Warning: Could not initialize Gemini client:", e)
        client = None
else:
    client = None
    if not genai:
        print("Warning: google.genai package not available.")
    if not GEMINI_KEY:
        print("Warning: GEMINI_API_KEY not set.")

def query_gemini(prompt: str) -> str | None:
    """
    Query Gemini LLM with a prompt. Returns string reply or None.
    """
    if not client or not GEMINI_KEY:
        return None
    try:
        gen_response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return getattr(gen_response, "text", str(gen_response))
    except Exception as e:
        print("LLM (Gemini) error:", e)
        return None
