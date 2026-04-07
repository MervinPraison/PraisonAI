
def search_web(query: str) -> str:
    """Search the web for information.
    
    Args:
        query: The search query
        
    Returns:
        Search results
    """
    return f"Web search results for: {query}"

def get_weather(location: str) -> str:
    """Get weather information for a location.
    
    Args:
        location: The location to get weather for
        
    Returns:
        Weather information
    """
    return f"Weather in {location}: Sunny, 25°C"

def calculate(expression: str) -> str:
    """Perform a calculation.
    
    Args:
        expression: Mathematical expression to evaluate
        
    Returns:
        Calculation result
    """
    try:
        result = eval(expression)
        return f"Result: {result}"
    except:
        return "Invalid expression"
