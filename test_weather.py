# test_weather.py
from services.llm_service import get_current_temperature

if __name__ == "__main__":
    city = "Ranchi"
    try:
        weather = get_current_temperature(city)
        print(f"✅ Weather data for {city}: {weather}")
    except Exception as e:
        print(f"❌ Error: {e}")
