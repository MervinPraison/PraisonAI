"""YFinance tools for stock market data.

Usage:
from praisonaiagents.tools import get_stock_price, get_stock_info
price = get_stock_price("AAPL")
info = get_stock_info("AAPL")

or 
from praisonaiagents.tools import yfinance
price = yfinance.get_stock_price("AAPL")
info = yfinance.get_stock_info("AAPL")
"""

from typing import List, Dict, Optional, Any
import logging
from importlib import util
from datetime import datetime

class YFinanceTools:
    """A comprehensive tool for financial data analysis using yfinance"""

    def __init__(self):
        """Initialize YFinanceTools"""
        self._tickers = {}

    def _get_yfinance(self):
        """Get yfinance module, installing if needed"""
        if util.find_spec('yfinance') is None:
            error_msg = "yfinance package is not available. Please install it using: pip install yfinance"
            logging.error(error_msg)
            return None
        import yfinance as yf
        return yf

    def _get_ticker(self, symbol: str):
        """Get or create ticker instance"""
        if symbol not in self._tickers:
            yf = self._get_yfinance()
            if yf is None:
                return None
            self._tickers[symbol] = yf.Ticker(symbol)
        return self._tickers[symbol]

    def get_stock_price(self, symbol: str) -> Dict[str, float]:
        """
        Get current stock price and related price metrics
        
        Args:
            symbol (str): Stock ticker symbol
            
        Returns:
            Dict[str, float]: Current price information
        """
        try:
            ticker = self._get_ticker(symbol)
            if ticker is None:
                return {"error": "yfinance package not available"}

            info = ticker.info
            return {
                'symbol': symbol,
                'price': info.get('regularMarketPrice', 0.0),
                'open': info.get('regularMarketOpen', 0.0),
                'high': info.get('regularMarketDayHigh', 0.0),
                'low': info.get('regularMarketDayLow', 0.0),
                'volume': info.get('regularMarketVolume', 0),
                'previous_close': info.get('regularMarketPreviousClose', 0.0),
                'change': info.get('regularMarketChange', 0.0),
                'change_percent': info.get('regularMarketChangePercent', 0.0)
            }
        except Exception as e:
            error_msg = f"Error getting stock price for {symbol}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_stock_info(self, symbol: str) -> Dict:
        """
        Get detailed information about a stock
        
        Args:
            symbol (str): Stock ticker symbol
            
        Returns:
            Dict: Stock information including company details and key metrics
        """
        try:
            ticker = self._get_ticker(symbol)
            if ticker is None:
                return {"error": "yfinance package not available"}

            info = ticker.info
            
            relevant_info = {
                "longName": info.get("longName"),
                "symbol": info.get("symbol"),
                "sector": info.get("sector"), 
                "industry": info.get("industry"),
                "country": info.get("country"),
                "marketCap": info.get("marketCap"),
                "currentPrice": info.get("currentPrice"),
                "currency": info.get("currency"),
                "exchange": info.get("exchange"),
                "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "dividendYield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "volume": info.get("volume"),
                "averageVolume": info.get("averageVolume"),
                "sharesOutstanding": info.get("sharesOutstanding"),
                "website": info.get("website"),
                "longBusinessSummary": info.get("longBusinessSummary")
            }
            return {k: v for k, v in relevant_info.items() if v is not None}
        except Exception as e:
            error_msg = f"Error fetching stock info: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_historical_data(
        self, 
        symbol: str, 
        period: str = "1y",
        interval: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data for a stock
        
        Args:
            symbol (str): Stock ticker symbol
            period (str): Data period e.g. 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
            interval (str): Data interval e.g. 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
            start (datetime, optional): Start date for data
            end (datetime, optional): End date for data
            
        Returns:
            List[Dict[str, Any]]: List of historical price data points
        """
        try:
            ticker = self._get_ticker(symbol)
            if ticker is None:
                return [{"error": "yfinance package not available"}]

            hist = ticker.history(period=period, interval=interval, start=start, end=end)
            data = hist.reset_index().to_dict('records')
            
            # Convert timestamps to ISO format strings
            for record in data:
                if 'Date' in record and hasattr(record['Date'], 'isoformat'):
                    record['Date'] = record['Date'].isoformat()
                if 'Datetime' in record and hasattr(record['Datetime'], 'isoformat'):
                    record['Datetime'] = record['Datetime'].isoformat()
            return data
        except Exception as e:
            error_msg = f"Error fetching historical data: {str(e)}"
            logging.error(error_msg)
            return [{"error": error_msg}]

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("YFinanceTools Demonstration")
    print("==================================================\n")

    try:
        yf_tools = YFinanceTools()

        # 1. Basic Stock Information
        print("1. Basic Stock Information for AAPL")
        print("------------------------------")
        info = yf_tools.get_stock_info("AAPL")
        if "error" not in info:
            print(f"Company: {info.get('longName')}")
            print(f"Sector: {info.get('sector')}")
            print(f"Industry: {info.get('industry')}")
            print(f"Country: {info.get('country')}\n")
        else:
            print(f"Error: {info['error']}\n")

        # 2. Current Price Data
        print("2. Current Price Data")
        print("------------------------------")
        price_data = yf_tools.get_stock_price("AAPL")
        if "error" not in price_data:
            print(f"Current Price: ${price_data.get('price', 'N/A')}")
            print(f"Previous Close: ${price_data.get('previous_close', 'N/A')}")
            print(f"Day Range: ${price_data.get('low', 'N/A')} - ${price_data.get('high', 'N/A')}\n")
        else:
            print(f"Error: {price_data['error']}\n")

        # 3. Historical Data
        print("3. Historical Data (Last 5 Days)")
        print("------------------------------")
        hist_data = yf_tools.get_historical_data("AAPL", period="5d")
        if not any("error" in d for d in hist_data):
            for day in hist_data:
                print(f"Date: {day.get('Date')}, Close: ${day.get('Close', 'N/A'):.2f}")
            print()
        else:
            print(f"{hist_data[0]['error']}\n")

        # 4. Multi-Stock Example
        print("5. Multi-Stock Current Prices")
        print("------------------------------")
        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            price_data = yf_tools.get_stock_price(symbol)
            if "error" not in price_data:
                print(f"{symbol}: ${price_data.get('price', 'N/A')}")
            else:
                print(f"{symbol}: Error fetching price")
        print()

    except Exception as e:
        print(f"Error: {str(e)}")

    print("==================================================")
    print("Analysis Complete")
    print("==================================================")