"""FXMacroData macroeconomic and FX data tools.

FXMacroData serves official central-bank and statistics-agency releases
(CPI, GDP, policy rates, payrolls, ...) per currency, along with release
calendars, FX rates, CFTC positioning and commodity prices.

USD indicators, the USD catalogue and the USD calendar work without an API
key. Keyless indicator data is delayed by 15 minutes (the response carries a
``freemium_delay`` object) and covers the last 90 days. Set the
FXMACRODATA_API_KEY environment variable for other currencies, FX rates and
commodities.

Usage:
    from praisonaiagents.tools import fxmacrodata_indicator, fxmacrodata_calendar

    cpi = fxmacrodata_indicator("usd", "inflation", limit=12)
    upcoming = fxmacrodata_calendar("usd")

    # Or use the class directly
    from praisonaiagents.tools import FXMacroDataTools
    fx = FXMacroDataTools()
    slugs = fx.catalogue("usd")

    # A configured instance's bound methods work as agent tools too; they are
    # named fxmacrodata_indicator etc., the same as the module functions.
    fx = FXMacroDataTools(api_key="...", timeout=10)
    agent = Agent(tools=[fx.catalogue, fx.indicator, fx.calendar])

    # Async agents: fxmacrodata_indicator_async(...) or await fx.aindicator(...)
"""

from typing import Any, Dict, Optional
import asyncio
import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = "https://api.fxmacrodata.com/v1"
MAX_PAGE_SIZE = 100


class _NoRedirect(HTTPRedirectHandler):
    # The API key header must never follow a redirect to another host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_NoRedirect)


def _segment(value: str) -> str:
    return quote(str(value).strip().lower(), safe="")


class FXMacroDataTools:
    """Macroeconomic, FX and release-calendar data from the FXMacroData API.

    Responses are returned as the API sends them, so field names match the
    API reference. Failures are returned as ``{"error": ..., "status_code": ...}``
    with the API's error body under ``response`` when there is one.

    Requires:
    - FXMACRODATA_API_KEY environment variable for anything beyond USD
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30):
        """Initialize FXMacroDataTools.

        Args:
            api_key: Optional API key. If not provided, uses FXMACRODATA_API_KEY env var.
            timeout: Request timeout in seconds
        """
        self._api_key = api_key
        self._timeout = timeout

    def _get_api_key(self) -> Optional[str]:
        """Get API key from instance or environment."""
        api_key = self._api_key or os.environ.get("FXMACRODATA_API_KEY")
        return api_key.strip() if api_key else None

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        query = {}
        for key, value in (params or {}).items():
            if value is None:
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            query[key] = value

        url = BASE_URL + path
        if query:
            url += "?" + urlencode(query)

        headers = {"Accept": "application/json", "User-Agent": "praisonaiagents"}
        api_key = self._get_api_key()
        if api_key:
            if any(ord(char) < 33 or ord(char) == 127 for char in api_key):
                # Never echo the key: http.client's own error would include it.
                error_msg = "FXMacroData API key contains whitespace or control characters"
                logging.error(error_msg)
                return {"error": error_msg}
            headers["X-API-Key"] = api_key

        try:
            with _OPENER.open(Request(url, headers=headers), timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) == {"detail"}:
                detail = payload.get("detail") if isinstance(payload, dict) else None
                if not isinstance(detail, str):
                    detail = type(payload).__name__
                error_msg = f"Unexpected FXMacroData response: {detail}"
                logging.error(error_msg)
                return {"error": error_msg}
            return payload
        except HTTPError as e:
            body: Any = None
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                pass
            detail = body.get("detail") if isinstance(body, dict) else None
            if not isinstance(detail, str):
                detail = e.reason
            error_msg = f"FXMacroData request failed ({e.code}): {detail}"
            logging.error(error_msg)
            result: Dict[str, Any] = {"error": error_msg, "status_code": e.code}
            if body is not None:
                result["response"] = body
            return result
        except (URLError, TimeoutError) as e:
            error_msg = f"FXMacroData request failed: {getattr(e, 'reason', e)}"
            logging.error(error_msg)
            return {"error": error_msg}
        except ValueError as e:
            error_msg = f"Error parsing FXMacroData response: {e}"
            logging.error(error_msg)
            return {"error": error_msg}

    @staticmethod
    def _page_shape_error(page: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return an error dict if ``page`` lacks the shape that pagination reads."""
        pagination = page.get("pagination")
        next_offset = pagination.get("next_offset") if isinstance(pagination, dict) else None
        if (
            not isinstance(page.get("data") or [], list)
            or not isinstance(pagination or {}, dict)
            or (next_offset is not None and (type(next_offset) is not int or next_offset < 0))
        ):
            error_msg = "Unexpected FXMacroData response: malformed data or pagination"
            logging.error(error_msg)
            return {"error": error_msg}
        return None

    def _paged(self, path: str, params: Dict[str, Any], limit: int, offset: int) -> Dict[str, Any]:
        """Fetch ``limit`` rows, following the API's pagination past 100 rows."""
        limit = max(1, int(limit))
        start = max(0, int(offset))
        result = self._request(path, {**params, "limit": min(limit, MAX_PAGE_SIZE), "offset": start})
        if "error" in result or limit <= MAX_PAGE_SIZE:
            return result
        shape_error = self._page_shape_error(result)
        if shape_error:
            return shape_error

        rows = list(result.get("data") or [])
        pagination = result.get("pagination") or {}
        # Pin later pages to the first page's dataset so a refresh between
        # requests is rejected (409) instead of shifting the offsets.
        version = result.get("dataset_version")
        page_params = {**params, "dataset_version": version} if version else params
        page_offset, page_count = start, len(rows)
        while len(rows) < limit and pagination.get("has_more"):
            next_offset = pagination.get("next_offset")
            request_offset = next_offset if next_offset is not None else page_offset + page_count
            page = self._request(path, {**page_params, "limit": min(limit - len(rows), MAX_PAGE_SIZE), "offset": request_offset})
            if "error" in page:
                return page
            shape_error = self._page_shape_error(page)
            if shape_error:
                return shape_error
            page_rows = page.get("data") or []
            if not page_rows:
                break
            rows.extend(page_rows)
            page_offset, page_count = request_offset, len(page_rows)
            pagination = page.get("pagination") or {}

        result["data"] = rows
        if pagination:
            # Describe the combined rows, not the last page that was fetched.
            combined = {**pagination, "limit": limit, "offset": start, "returned_count": len(rows)}
            if combined.get("has_more"):
                next_offset = pagination.get("next_offset")
                combined["next_offset"] = next_offset if next_offset is not None else page_offset + page_count
            result["pagination"] = combined
        return result

    def indicator(
        self,
        currency: str,
        indicator: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get the release history of one macroeconomic indicator.

        Args:
            currency: Three-letter currency code, e.g. "usd", "eur", "jpy"
            indicator: Indicator slug from catalogue(), e.g. "inflation", "policy_rate", "gdp"
            start_date: Earliest observation date, YYYY-MM-DD
            end_date: Latest observation date, YYYY-MM-DD
            limit: Number of rows, most recent first (more than 100 is fetched page by page)
            offset: Rows to skip from the most recent

        Returns:
            Dict with series metadata and ``data`` rows (``date``, ``val``,
            ``announcement_datetime``, ...). Without a key, ``freemium_delay``
            reports releases withheld by the 15 minute delay.
        """
        path = f"/announcements/{_segment(currency)}/{_segment(indicator)}"
        params = {"start_date": start_date, "end_date": end_date}
        return self._paged(path, params, limit, offset)

    def catalogue(self, currency: str, include_coverage: bool = False) -> Dict[str, Any]:
        """List the indicators available for a currency.

        Args:
            currency: Three-letter currency code
            include_coverage: Include history and freshness details per indicator

        Returns:
            Dict keyed by indicator slug with name, unit and source
        """
        path = f"/data_catalogue/{_segment(currency)}"
        return self._request(path, {"include_coverage": include_coverage})

    def calendar(
        self,
        currency: str,
        indicator: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get scheduled release dates for a currency.

        Args:
            currency: Three-letter currency code
            indicator: Only return releases for this indicator slug
            start_date: First date, YYYY-MM-DD
            end_date: Last date, YYYY-MM-DD
            timezone: IANA timezone for local times, e.g. "Europe/London"

        Returns:
            Dict with ``data`` rows (``release``, ``name``,
            ``announcement_datetime_utc``, ``event_importance``, ...)
        """
        path = f"/calendar/{_segment(currency)}"
        params = {
            "indicator": indicator,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": timezone,
        }
        return self._request(path, params)

    def forex(
        self,
        base: str,
        quote: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get daily FX rates for a currency pair. Requires an API key.

        Args:
            base: Base currency, e.g. "eur"
            quote: Quote currency, e.g. "usd"
            start_date: First date, YYYY-MM-DD
            end_date: Last date, YYYY-MM-DD
            limit: Number of rows, most recent first (more than 100 is fetched page by page)
            offset: Rows to skip from the most recent

        Returns:
            Dict with ``data`` rows of dated rates
        """
        path = f"/forex/{_segment(base)}/{_segment(quote)}"
        params = {"start_date": start_date, "end_date": end_date}
        return self._paged(path, params, limit, offset)

    def cot(
        self,
        currency: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get CFTC Commitments of Traders positioning for a currency.

        Args:
            currency: Three-letter currency code (USD works without an API key)
            start_date: First report date, YYYY-MM-DD
            end_date: Last report date, YYYY-MM-DD
            limit: Number of weekly rows, most recent first
            offset: Rows to skip from the most recent

        Returns:
            Dict with ``data`` rows of weekly positioning
        """
        path = f"/cot/{_segment(currency)}"
        params = {"start_date": start_date, "end_date": end_date}
        return self._paged(path, params, limit, offset)

    def commodity(
        self,
        indicator: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get price history for a commodity. Requires an API key.

        Args:
            indicator: Commodity slug, e.g. "gold", "oil_brent", "natural_gas"
            start_date: First date, YYYY-MM-DD
            end_date: Last date, YYYY-MM-DD
            limit: Number of rows, most recent first
            offset: Rows to skip from the most recent

        Returns:
            Dict with ``data`` rows of dated prices
        """
        path = f"/commodities/{_segment(indicator)}"
        params = {"start_date": start_date, "end_date": end_date}
        return self._paged(path, params, limit, offset)

    # Async variants. Each runs the stdlib request in a worker thread, so an
    # async agent's event loop is never blocked and no extra dependency is needed.

    async def aindicator(
        self,
        currency: str,
        indicator: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Async version of indicator(). See indicator() for documentation."""
        return await asyncio.to_thread(self.indicator, currency, indicator, start_date, end_date, limit, offset)

    async def acatalogue(self, currency: str, include_coverage: bool = False) -> Dict[str, Any]:
        """Async version of catalogue(). See catalogue() for documentation."""
        return await asyncio.to_thread(self.catalogue, currency, include_coverage)

    async def acalendar(
        self,
        currency: str,
        indicator: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async version of calendar(). See calendar() for documentation."""
        return await asyncio.to_thread(self.calendar, currency, indicator, start_date, end_date, timezone)

    async def aforex(
        self,
        base: str,
        quote: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Async version of forex(). See forex() for documentation."""
        return await asyncio.to_thread(self.forex, base, quote, start_date, end_date, limit, offset)

    async def acot(
        self,
        currency: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Async version of cot(). See cot() for documentation."""
        return await asyncio.to_thread(self.cot, currency, start_date, end_date, limit, offset)

    async def acommodity(
        self,
        indicator: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Async version of commodity(). See commodity() for documentation."""
        return await asyncio.to_thread(self.commodity, indicator, start_date, end_date, limit, offset)


# Agents name a callable tool by its __name__, which for a bound method such as
# FXMacroDataTools(api_key=...).indicator would be the bare "indicator". Give the
# methods the module tool names so a configured instance gets the same tool
# names, and the same external-content fencing (tools/trust.py), as the module
# functions, without marking unrelated tools that happen to share a short name.
for _method, _tool_name in {
    "indicator": "fxmacrodata_indicator",
    "catalogue": "fxmacrodata_catalogue",
    "calendar": "fxmacrodata_calendar",
    "forex": "fxmacrodata_forex",
    "cot": "fxmacrodata_cot",
    "commodity": "fxmacrodata_commodity",
}.items():
    getattr(FXMacroDataTools, _method).__name__ = _tool_name
    getattr(FXMacroDataTools, "a" + _method).__name__ = _tool_name + "_async"
del _method, _tool_name


def fxmacrodata_indicator(
    currency: str,
    indicator: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get the release history of a macroeconomic indicator (CPI, GDP, policy rate, ...).

    USD works without an API key (15 minute delay, last 90 days).

    Args:
        currency: Three-letter currency code, e.g. "usd", "eur", "jpy"
        indicator: Indicator slug from fxmacrodata_catalogue, e.g. "inflation", "policy_rate"
        start_date: Earliest observation date, YYYY-MM-DD
        end_date: Latest observation date, YYYY-MM-DD
        limit: Number of rows, most recent first
        offset: Rows to skip from the most recent

    Returns:
        Dict with series metadata and ``data`` rows
    """
    return FXMacroDataTools().indicator(
        currency=currency,
        indicator=indicator,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


def fxmacrodata_catalogue(currency: str, include_coverage: bool = False) -> Dict[str, Any]:
    """List the indicator slugs available for a currency.

    Args:
        currency: Three-letter currency code
        include_coverage: Include history and freshness details per indicator

    Returns:
        Dict keyed by indicator slug
    """
    return FXMacroDataTools().catalogue(currency=currency, include_coverage=include_coverage)


def fxmacrodata_calendar(
    currency: str,
    indicator: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """Get upcoming and recent release dates for a currency.

    Args:
        currency: Three-letter currency code
        indicator: Only return releases for this indicator slug
        start_date: First date, YYYY-MM-DD
        end_date: Last date, YYYY-MM-DD
        timezone: IANA timezone for local times

    Returns:
        Dict with ``data`` rows of scheduled releases
    """
    return FXMacroDataTools().calendar(
        currency=currency,
        indicator=indicator,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
    )


def fxmacrodata_forex(
    base: str,
    quote: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get daily FX rates for a currency pair, e.g. base="eur", quote="usd". Requires an API key.

    Args:
        base: Base currency
        quote: Quote currency
        start_date: First date, YYYY-MM-DD
        end_date: Last date, YYYY-MM-DD
        limit: Number of rows, most recent first
        offset: Rows to skip from the most recent

    Returns:
        Dict with ``data`` rows of dated rates
    """
    return FXMacroDataTools().forex(
        base=base,
        quote=quote,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


def fxmacrodata_cot(
    currency: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get CFTC Commitments of Traders positioning for a currency.

    Args:
        currency: Three-letter currency code (USD works without an API key)
        start_date: First report date, YYYY-MM-DD
        end_date: Last report date, YYYY-MM-DD
        limit: Number of weekly rows, most recent first
        offset: Rows to skip from the most recent

    Returns:
        Dict with ``data`` rows of weekly positioning
    """
    return FXMacroDataTools().cot(
        currency=currency,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


def fxmacrodata_commodity(
    indicator: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get price history for a commodity such as "gold" or "oil_wti". Requires an API key.

    Args:
        indicator: Commodity slug
        start_date: First date, YYYY-MM-DD
        end_date: Last date, YYYY-MM-DD
        limit: Number of rows, most recent first
        offset: Rows to skip from the most recent

    Returns:
        Dict with ``data`` rows of dated prices
    """
    return FXMacroDataTools().commodity(
        indicator=indicator,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


async def fxmacrodata_indicator_async(
    currency: str,
    indicator: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Async version of fxmacrodata_indicator. See fxmacrodata_indicator() for documentation."""
    return await FXMacroDataTools().aindicator(currency, indicator, start_date, end_date, limit, offset)


async def fxmacrodata_catalogue_async(currency: str, include_coverage: bool = False) -> Dict[str, Any]:
    """Async version of fxmacrodata_catalogue. See fxmacrodata_catalogue() for documentation."""
    return await FXMacroDataTools().acatalogue(currency, include_coverage)


async def fxmacrodata_calendar_async(
    currency: str,
    indicator: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """Async version of fxmacrodata_calendar. See fxmacrodata_calendar() for documentation."""
    return await FXMacroDataTools().acalendar(currency, indicator, start_date, end_date, timezone)


async def fxmacrodata_forex_async(
    base: str,
    quote: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Async version of fxmacrodata_forex. See fxmacrodata_forex() for documentation."""
    return await FXMacroDataTools().aforex(base, quote, start_date, end_date, limit, offset)


async def fxmacrodata_cot_async(
    currency: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Async version of fxmacrodata_cot. See fxmacrodata_cot() for documentation."""
    return await FXMacroDataTools().acot(currency, start_date, end_date, limit, offset)


async def fxmacrodata_commodity_async(
    indicator: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Async version of fxmacrodata_commodity. See fxmacrodata_commodity() for documentation."""
    return await FXMacroDataTools().acommodity(indicator, start_date, end_date, limit, offset)


# Alias for simple usage: from praisonaiagents.tools import fxmacrodata
fxmacrodata = fxmacrodata_indicator
