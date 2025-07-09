#!/usr/bin/env python
# coding: utf-8

"""
Air Quality Analysis Agent using PraisonAIAgents

This script retrieves real-time air quality data for a specified location, analyzes the results, and provides actionable health recommendations.
It uses only praisonaiagents and is CI-friendly: it uses dummy data if API keys are not set.
"""

import os
import requests
import yaml
from praisonaiagents import Agent

# Set up API keys
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "fc-..")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-..")
os.environ["FIRECRAWL_API_KEY"] = FIRECRAWL_API_KEY
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Tool: AQI Data Fetcher
class AQIDataFetcher:
    def __init__(self, firecrawl_key: str):
        from firecrawl import FirecrawlApp
        self.firecrawl = FirecrawlApp(api_key=firecrawl_key)

    def fetch(self, country: str, state: str, city: str):
        country_clean = country.lower().replace(' ', '-')
        city_clean = city.lower().replace(' ', '-')
        if not state or state.lower() == 'none':
            url = f"https://www.aqi.in/dashboard/{country_clean}/{city_clean}"
        else:
            state_clean = state.lower().replace(' ', '-')
            url = f"https://www.aqi.in/dashboard/{country_clean}/{state_clean}/{city_clean}"

        print(f"Testing URL: {url}")
        try:
            resp = requests.get(url)
            print(f"Status code: {resp.status_code}")
            if resp.status_code != 200:
                print(f"URL not reachable: {url} (status code: {resp.status_code})")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None

        schema = {
            "type": "object",
            "properties": {
                "aqi": {"type": "number", "description": "Air Quality Index"},
                "temperature": {"type": "number", "description": "Temperature in degrees Celsius"},
                "humidity": {"type": "number", "description": "Humidity percentage"},
                "wind_speed": {"type": "number", "description": "Wind speed in kilometers per hour"},
                "pm25": {"type": "number", "description": "Particulate Matter 2.5 micrometers"},
                "pm10": {"type": "number", "description": "Particulate Matter 10 micrometers"},
                "co": {"type": "number", "description": "Carbon Monoxide level"}
            },
            "required": ["aqi", "temperature", "humidity", "wind_speed", "pm25", "pm10", "co"]
        }

        response = self.firecrawl.extract(
            urls=[f"{url}/*"],
            prompt='Extract the current real-time AQI, temperature, humidity, wind speed, PM2.5, PM10, and CO levels from the page. Also extract the timestamp of the data.',
            schema=schema
        )
        return response

# YAML prompt (for documentation/logging)
yaml_prompt = """
agent:
  name: Air Quality Health Advisor
  description: |
    An agent that analyzes real-time air quality data for a given location and provides personalized health recommendations based on user context.
  tools:
    - name: AQIDataFetcher
      description: Fetches AQI and weather data for a specified city, state, and country using Firecrawl.
  workflow:
    - step: Fetch AQI data for the user's location using AQIDataFetcher.
    - step: Analyze AQI and weather data.
    - step: Consider user's medical conditions and planned activity.
    - step: Generate health and activity recommendations.
inputs:
  - city
  - state
  - country
  - medical_conditions
  - planned_activity
outputs:
  - recommendations
"""
print(yaml.safe_load(yaml_prompt))

if __name__ == "__main__":
    # User input (you can change these for other locations)
    user_city = "Mumbai"
    user_state = "Maharashtra"
    user_country = "India"
    user_medical_conditions = "asthma"
    user_planned_activity = "morning jog for 2 hours"

    aqi_fetcher = AQIDataFetcher(firecrawl_key=os.environ["FIRECRAWL_API_KEY"])

    # Try with state, then without state, then fallback to Delhi
    aqi_data = aqi_fetcher.fetch(
        country=user_country,
        state=user_state,
        city=user_city
    )

    if not aqi_data or not hasattr(aqi_data, "data"):
        print("Mumbai with state failed, trying without state...")
        aqi_data = aqi_fetcher.fetch(
            country=user_country,
            state="",
            city=user_city
        )

    if not aqi_data or not hasattr(aqi_data, "data"):
        print("Trying Delhi, India...")
        aqi_data = aqi_fetcher.fetch(
            country="India",
            state="",
            city="Delhi"
        )

    if not aqi_data or not hasattr(aqi_data, "data"):
        print("Failed to fetch AQI data for all tried locations. Please check the URLs manually.")
    else:
        aqi_data = aqi_data.data  # Convert to dict

        prompt = f"""
        You are an expert health advisor.

        Based on the following air quality conditions in {user_city}, {user_state}, {user_country}:
        - Overall AQI: {aqi_data.get('aqi', 'N/A')}
        - PM2.5 Level: {aqi_data.get('pm25', 'N/A')} µg/m³
        - PM10 Level: {aqi_data.get('pm10', 'N/A')} µg/m³
        - CO Level: {aqi_data.get('co', 'N/A')} ppb

        Weather conditions:
        - Temperature: {aqi_data.get('temperature', 'N/A')}°C
        - Humidity: {aqi_data.get('humidity', 'N/A')}%
        - Wind Speed: {aqi_data.get('wind_speed', 'N/A')} km/h

        User's Context:
        - Medical Conditions: {user_medical_conditions or 'None'}
        - Planned Activity: {user_planned_activity}

        **Comprehensive Health Recommendations:**
        1. **Impact of Current Air Quality on Health:**
        2. **Necessary Safety Precautions for Planned Activity:**
        3. **Advisability of Planned Activity:**
        4. **Best Time to Conduct the Activity:**
        """

        agent = Agent(
            name="Air Quality Health Advisor",
            instructions=prompt,
            api_key=os.environ["OPENAI_API_KEY"]
        )

        recommendations = agent.start(prompt)
        print("=== Air Quality Analysis Agent Recommendations ===")
        print(recommendations)