# PraisonAI Tools Guide

Welcome to the PraisonAI Tools directory! This guide will help you understand how our tools work and how to create new ones, whether you're a beginner or an experienced programmer.

## What is a Tool?

A tool is a piece of code that helps our AI agents perform specific tasks. Think of tools as special abilities that we give to our agents. For example:
- An internet search tool lets agents search the web
- A stock market tool lets agents check stock prices
- A weather tool lets agents check the weather

## Creating New Tools: The Two Approaches

### 1. Function-Based Approach (Simple Tools)

Best for simple tools that do one specific thing. Like a calculator that just adds numbers.

**When to use:**
- Tool does one simple task
- Doesn't need to remember information between uses
- Doesn't need to share information with other tools
- Quick, one-time operations

**Example:**
```python
def internet_search(query: str):
    # Search the internet and return results
    return search_results
```

**Usage:**
```python
from praisonaiagents.tools import internet_search

results = internet_search("AI news")
```

### 2. Class-Based Approach (Complex Tools)

Best for tools that do multiple related things or need to remember information. Like a smart calculator that remembers your previous calculations and can do many different math operations.

**When to use:**
- Tool has multiple related functions
- Needs to remember or share information
- Needs to manage resources efficiently
- Has complex setup requirements

**Example:**
```python
class StockTools:
    def get_stock_price(self, symbol):
        # Get current stock price
        return price
        
    def get_stock_info(self, symbol):
        # Get detailed stock information
        return info
```

**Usage:**
```python
from praisonaiagents.tools import get_stock_price, get_stock_info

price = get_stock_price("AAPL")
info = get_stock_info("AAPL")
```

## How to Choose Your Approach

Ask yourself these questions:

1. **Is your tool doing one simple thing?**
   - Yes → Use Function-Based Approach
   - No → Consider Class-Based Approach

2. **Does your tool need to remember information?**
   - Yes → Use Class-Based Approach
   - No → Use Function-Based Approach

3. **Are your tool's operations related to each other?**
   - Yes → Use Class-Based Approach
   - No → Use Function-Based Approach

4. **Does your tool need to manage resources efficiently?**
   - Yes → Use Class-Based Approach
   - No → Use Function-Based Approach

## Real-World Examples

### Internet Search Tool (Function-Based)
- Does one thing: searches the internet
- Doesn't need to remember previous searches
- Each search is independent
- Simple input/output operation

### SearxNG Search Tool (Function-Based)
- Privacy-focused web search using local SearxNG instance
- Simple search operation with customizable parameters
- Each search is independent and secure
- Alternative to traditional search engines for privacy

### Stock Market Tool (Class-Based)
- Does multiple things: check prices, get company info, get historical data
- Remembers stock information to avoid repeated downloads
- Operations are related (all about stocks)
- Manages connections efficiently

## Getting Started

1. **Choose Your Approach** based on the guidelines above

2. **Create Your Tool File**:
   - Name it descriptively (e.g., `weather_tools.py`)
   - Place it in the `praisonaiagents/tools` directory

3. **Write Your Tool**:
   - Add clear documentation
   - Include type hints for better understanding
   - Handle errors gracefully

4. **Test Your Tool**:
   - Make sure it works as expected
   - Test error cases
   - Check performance

## Best Practices

1. **Documentation**:
   - Explain what your tool does
   - Provide examples
   - List any requirements

2. **Error Handling**:
   - Always handle possible errors
   - Return helpful error messages
   - Don't let your tool crash

3. **Performance**:
   - Keep it efficient
   - Don't waste resources
   - Cache when helpful

4. **User-Friendly**:
   - Make it easy to use
   - Use clear function/method names
   - Keep it simple

## Need Help?

- Check existing tools for examples
- Ask in our community
- Read the documentation
- Don't hesitate to ask questions!

Remember: The goal is to make tools that are easy to use and maintain. Choose the approach that makes the most sense for your specific tool's needs.
