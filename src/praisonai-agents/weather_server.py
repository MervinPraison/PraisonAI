#!/usr/bin/env python
from mcp.server.fastmcp import FastMCP
import logging
import datetime
from typing import Dict, List, Union

# Set up logging
logging.basicConfig(level=logging.INFO, filename="weather_server.log")
logger = logging.getLogger("weather-server")

# Initialize FastMCP server for weather tools
mcp = FastMCP("weather-tools")

# Mock weather data for cities
MOCK_WEATHER_DATA = {
    "london": {
        "temp": 15,
        "feels_like": 13,
        "temp_min": 12,
        "temp_max": 17,
        "humidity": 76,
        "description": "Cloudy with occasional rain",
        "wind_speed": 12,
        "country": "GB"
    },
    "paris": {
        "temp": 18,
        "feels_like": 17,
        "temp_min": 16,
        "temp_max": 20,
        "humidity": 65,
        "description": "Partly cloudy",
        "wind_speed": 8,
        "country": "FR"
    },
    "new york": {
        "temp": 22,
        "feels_like": 24,
        "temp_min": 20,
        "temp_max": 25,
        "humidity": 58,
        "description": "Clear sky",
        "wind_speed": 10,
        "country": "US"
    },
    "tokyo": {
        "temp": 26,
        "feels_like": 28,
        "temp_min": 24,
        "temp_max": 29,
        "humidity": 72,
        "description": "Humid and warm",
        "wind_speed": 7,
        "country": "JP"
    },
    "sydney": {
        "temp": 20,
        "feels_like": 19,
        "temp_min": 17,
        "temp_max": 23,
        "humidity": 60,
        "description": "Sunny with light breeze",
        "wind_speed": 15,
        "country": "AU"
    }
}

@mcp.tool()
def get_weather(location: Union[str, List[str]]) -> Dict:
    """Get current weather data for one or more locations.

    Args:
        location: City name (str) or list of city names (List[str]) to get weather for
    
    Returns:
        Dict with weather data for each location or error message
    """
    def get_single_location_weather(loc: str) -> Dict:
        """Helper function to get weather for a single location"""
        loc = loc.lower().strip()
        if loc in MOCK_WEATHER_DATA:
            weather_data = MOCK_WEATHER_DATA[loc].copy()
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            weather_data["time"] = current_time
            weather_data["city"] = loc.title()
            return weather_data
        return {"city": loc.title(), "error": "Location not found in weather database"}
    
    logger.info(f"Getting weather data for {location}")
    
    # Handle list of locations
    if isinstance(location, list):
        results = {}
        for loc in location:
            if isinstance(loc, str):
                results[loc] = get_single_location_weather(loc)
        return {"results": results}
    
    # Handle single location
    if isinstance(location, str):
        return get_single_location_weather(location)
    
    return {"error": "Invalid location format. Please provide a string or list of strings."}

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
