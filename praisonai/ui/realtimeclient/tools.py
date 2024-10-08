import yfinance as yf
import chainlit as cl
import plotly
import json
from tavily import TavilyClient
from crawl4ai import WebCrawler
import os
import logging
import asyncio
from openai import OpenAI
import base64
from io import BytesIO

# Set up logging
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger.setLevel(log_level)

# Set Tavily API key
tavily_api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=tavily_api_key) if tavily_api_key else None

# Set up OpenAI client
openai_client = OpenAI()

query_stock_price_def = {
    "name": "query_stock_price",
    "description": "Queries the latest stock price information for a given stock symbol.",
    "parameters": {
      "type": "object",
      "properties": {
        "symbol": {
          "type": "string",
          "description": "The stock symbol to query (e.g., 'AAPL' for Apple Inc.)"
        },
        "period": {
          "type": "string",
          "description": "The time period for which to retrieve stock data (e.g., '1d' for one day, '1mo' for one month)"
        }
      },
      "required": ["symbol", "period"]
    }
}

async def query_stock_price_handler(symbol, period):
    """
    Queries the latest stock price information for a given stock symbol.
    """
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period=period)
        if hist.empty:
            return {"error": "No data found for the given symbol."}
        return hist.to_json()
 
    except Exception as e:
        return {"error": str(e)}

query_stock_price = (query_stock_price_def, query_stock_price_handler)

draw_plotly_chart_def = {
    "name": "draw_plotly_chart",
    "description": "Draws a Plotly chart based on the provided JSON figure and displays it with an accompanying message.",
    "parameters": {
      "type": "object",
      "properties": {
        "message": {
          "type": "string",
          "description": "The message to display alongside the chart"
        },
        "plotly_json_fig": {
          "type": "string",
          "description": "A JSON string representing the Plotly figure to be drawn"
        }
      },
      "required": ["message", "plotly_json_fig"]
    }
}

async def draw_plotly_chart_handler(message: str, plotly_json_fig):
    fig = plotly.io.from_json(plotly_json_fig)
    elements = [cl.Plotly(name="chart", figure=fig, display="inline")]

    await cl.Message(content=message, elements=elements).send()
    return {"status": "success"}  # Add a return value

draw_plotly_chart = (draw_plotly_chart_def, draw_plotly_chart_handler)

tavily_web_search_def = {
    "name": "tavily_web_search",
    "description": "Search the web using Tavily API and crawl the resulting URLs",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
}

async def tavily_web_search_handler(query):
    if not tavily_client:
        return json.dumps({
            "query": query,
            "error": "Tavily API key is not set. Web search is unavailable."
        })
    
    response = tavily_client.search(query)
    logger.debug(f"Tavily search response: {response}")

    # Create an instance of WebCrawler
    crawler = WebCrawler()

    # Warm up the crawler (load necessary models)
    crawler.warmup()

    # Prepare the results
    results = []
    for result in response.get('results', []):
        url = result.get('url')
        if url:
            try:
                # Run the crawler on each URL
                crawl_result = crawler.run(url=url)
                results.append({
                    "content": result.get('content'),
                    "url": url,
                    "full_content": crawl_result.markdown
                })
            except Exception as e:
                logger.error(f"Error crawling {url}: {str(e)}")
                results.append({
                    "content": result.get('content'),
                    "url": url,
                    "full_content": "Error: Unable to crawl this URL"
                })

    return json.dumps({
        "query": query,
        "results": results
    })

tavily_web_search = (tavily_web_search_def, tavily_web_search_handler)

# New image generation tool
generate_image_def = {
    "name": "generate_image",
    "description": "Generate an image based on a text prompt using DALL-E 3",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "The text prompt to generate the image"},
            "size": {"type": "string", "description": "Image size (1024x1024, 1024x1792, or 1792x1024)", "default": "1024x1024"},
            "quality": {"type": "string", "description": "Image quality (standard or hd)", "default": "standard"},
        },
        "required": ["prompt"]
    }
}

async def generate_image_handler(prompt, size="1024x1024", quality="standard"):
    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )

        image_url = response.data[0].url

        # Download the image
        import requests
        image_content = requests.get(image_url).content

        # Convert image to base64
        image_base64 = base64.b64encode(image_content).decode('utf-8')

        # Create a Chainlit Image element
        image_element = cl.Image(content=image_content, name="generated_image", display="inline")

        # Send the image in a Chainlit message
        await cl.Message(content=f"Generated image for prompt: '{prompt}'", elements=[image_element]).send()

        return {"status": "success", "message": "Image generated and displayed"}
    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        return {"status": "error", "message": str(e)}

generate_image = (generate_image_def, generate_image_handler)

tools = [query_stock_price, draw_plotly_chart, tavily_web_search, generate_image]