import time
import random

def get_current_weather(location: str) -> dict:
    """Gets the current weather for a specific location."""
    print(f"EXECUTING TOOL: get_current_weather with location='{location}'")
    time.sleep(0.5) # Simulate network latency
    conditions = ["Sunny", "Cloudy", "Rainy", "Windy"]
    return {
        "location": location,
        "temperature": f"{random.randint(5, 35)}°C",
        "condition": random.choice(conditions)
    }