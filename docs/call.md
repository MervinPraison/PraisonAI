# PraisonAI Call

<iframe width="560" height="315" src="https://www.youtube.com/embed/m1cwrUG2iAk" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>

## AI Customer Service

PraisonAI Call is a feature that enables voice-based interaction with AI models through phone calls. This functionality allows users to have natural conversations with AI agents over traditional phone lines.

## Installation

### Step 1

```bash
pip install "praisonai[call]"
export OPENAI_API_KEY="enter your openai api key here"
praisonai call --public
```

### Step 2

Buy a number
https://dashboard.praison.ai/

### Step 3

Enter the Public URL in the PraisonAI Dashboard phone number field

## Features

- Make and receive phone calls with AI agents
- Natural language processing for voice interactions
- Support for multiple phone carriers and providers
- Call recording and transcription capabilities
- Integration with other PraisonAI features

## Adding Tools

1. Create a file called `tools.py`
2. Add the following code:
```python
import yfinance as yf

# Get Stock Price definition
get_stock_price_def = {
    "name": "get_stock_price",
    "description": "Get the current stock price for a given ticker symbol",
    "parameters": {
        "type": "object", 
        "properties": {
            "ticker_symbol": {
                "type": "string", 
                "description": "The ticker symbol of the stock (e.g., AAPL, GOOGL)"
            }
        }, 
        "required": ["ticker_symbol"]
    }
}

# Get Stock Price function / Tool
async def get_stock_price_handler(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="1d")
        if hist.empty:
            return {"error": f"No data found for ticker {ticker_symbol}"}
        current_price = hist['Close'].iloc[-1]  # Using -1 is safer than 0
        return {"price": str(current_price)}
    except Exception as e:
        return {"error": str(e)}



get_stock_price = (get_stock_price_def, get_stock_price_handler)
tools = [
    get_stock_price
]
```

3. ```bash
pip install yfinance
praisonai call --public
```

## Manage Google Calendar Events

See [Google Calendar Tools](tools/googlecalendar.md)
