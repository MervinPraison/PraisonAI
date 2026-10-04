"""Unit tests for the FXMacroData tools (HTTP is stubbed)."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from praisonaiagents.tools import fxmacrodata_tools as fxm
from praisonaiagents.tools.fxmacrodata_tools import FXMacroDataTools


def _response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class FakeOpener:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return _response(payload)


def _query(request):
    return {k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()}


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.delenv("FXMACRODATA_API_KEY", raising=False)


def test_indicator_without_key_returns_payload_unchanged():
    payload = {
        "currency": "USD",
        "indicator": "inflation",
        "freemium_delay": {"applied": True, "delay_minutes": 15, "withheld_count": 0},
        "pagination": {"limit": 2, "offset": 0, "has_more": True, "next_offset": 2},
        "data": [{"date": "2026-08-31", "val": 2.9}, {"date": "2026-07-31", "val": 2.7}],
    }
    opener = FakeOpener(payload)
    with patch.object(fxm, "_OPENER", opener):
        result = fxm.fxmacrodata_indicator("USD", "inflation", start_date="2026-01-01", limit=2)

    assert result == payload
    request = opener.requests[0]
    assert urlsplit(request.full_url).path == "/v1/announcements/usd/inflation"
    assert urlsplit(request.full_url).netloc == "api.fxmacrodata.com"
    assert _query(request) == {"start_date": "2026-01-01", "limit": "2", "offset": "0"}
    assert request.get_header("X-api-key") is None


def test_key_is_sent_as_header_not_query(monkeypatch):
    monkeypatch.setenv("FXMACRODATA_API_KEY", "test-key")
    opener = FakeOpener({"data": []})
    with patch.object(fxm, "_OPENER", opener):
        fxm.fxmacrodata_forex("eur", "usd")

    request = opener.requests[0]
    assert request.get_header("X-api-key") == "test-key"
    assert "test-key" not in request.full_url
    assert urlsplit(request.full_url).path == "/v1/forex/eur/usd"


def test_explicit_key_overrides_env(monkeypatch):
    monkeypatch.setenv("FXMACRODATA_API_KEY", "env-key")
    opener = FakeOpener({"data": []})
    with patch.object(fxm, "_OPENER", opener):
        FXMacroDataTools(api_key="arg-key").cot("usd")
    assert opener.requests[0].get_header("X-api-key") == "arg-key"


def test_limit_over_page_size_follows_pagination():
    first = {
        "currency": "USD",
        "freemium_delay": {"applied": True},
        "pagination": {"limit": 100, "offset": 0, "has_more": True, "next_offset": 100},
        "data": [{"date": str(i)} for i in range(100)],
    }
    second = {
        "pagination": {"limit": 50, "offset": 100, "has_more": True, "next_offset": 150},
        "data": [{"date": str(i)} for i in range(100, 150)],
    }
    opener = FakeOpener(first, second)
    with patch.object(fxm, "_OPENER", opener):
        result = fxm.fxmacrodata_indicator("usd", "non_farm_payrolls", limit=150)

    assert [_query(r)["offset"] for r in opener.requests] == ["0", "100"]
    assert [_query(r)["limit"] for r in opener.requests] == ["100", "50"]
    assert len(result["data"]) == 150
    assert result["freemium_delay"] == {"applied": True}
    assert result["pagination"]["next_offset"] == 150


def test_pagination_stops_when_no_more_rows():
    only = {
        "pagination": {"limit": 100, "offset": 0, "has_more": False},
        "data": [{"date": "2026-01-01"}],
    }
    opener = FakeOpener(only)
    with patch.object(fxm, "_OPENER", opener):
        result = fxm.fxmacrodata_commodity("gold", limit=500)
    assert len(opener.requests) == 1
    assert result["data"] == [{"date": "2026-01-01"}]


def test_catalogue_and_calendar_params():
    opener = FakeOpener({"inflation": {"name": "Inflation (CPI)"}}, {"data": []})
    with patch.object(fxm, "_OPENER", opener):
        catalogue = fxm.fxmacrodata_catalogue("usd", include_coverage=True)
        fxm.fxmacrodata_calendar("usd", indicator="inflation", timezone="Europe/London")

    assert catalogue == {"inflation": {"name": "Inflation (CPI)"}}
    assert urlsplit(opener.requests[0].full_url).path == "/v1/data_catalogue/usd"
    assert _query(opener.requests[0]) == {"include_coverage": "true"}
    assert urlsplit(opener.requests[1].full_url).path == "/v1/calendar/usd"
    assert _query(opener.requests[1]) == {"indicator": "inflation", "timezone": "Europe/London"}


def test_path_segments_are_escaped():
    opener = FakeOpener({"data": []})
    with patch.object(fxm, "_OPENER", opener):
        fxm.fxmacrodata_indicator("usd", "../forex/eur/usd?x=1")
    assert urlsplit(opener.requests[0].full_url).path == "/v1/announcements/usd/..%2Fforex%2Feur%2Fusd%3Fx%3D1"


def test_http_error_returns_error_dict_with_api_body():
    body = {
        "detail": "This endpoint requires an Individual or Business API key.",
        "code": "api_key_required",
        "subscribe_url": "https://fxmacrodata.com/subscribe",
    }
    error = HTTPError(
        "https://api.fxmacrodata.com/v1/forex/eur/usd", 401, "Unauthorized", {}, _response(body)
    )
    with patch.object(fxm, "_OPENER", FakeOpener(error)):
        result = fxm.fxmacrodata_forex("eur", "usd")

    assert result["status_code"] == 401
    assert "requires an Individual or Business API key" in result["error"]
    assert result["response"] == body


def test_validation_error_detail_list():
    body = {"detail": [{"loc": ["query", "limit"], "msg": "Input should be less than or equal to 100"}]}
    error = HTTPError("https://api.fxmacrodata.com/v1/x", 422, "Unprocessable Entity", {}, _response(body))
    with patch.object(fxm, "_OPENER", FakeOpener(error)):
        result = FXMacroDataTools().calendar("usd")
    assert result["status_code"] == 422
    assert "Unprocessable Entity" in result["error"]
    assert result["response"] == body


def test_network_error_returns_error_dict():
    with patch.object(fxm, "_OPENER", FakeOpener(URLError("timed out"))):
        result = fxm.fxmacrodata_catalogue("usd")
    assert result == {"error": "FXMacroData request failed: timed out"}


def test_redirects_are_not_followed():
    assert fxm._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.com/") is None


def test_lazy_exports():
    from praisonaiagents import tools
    from praisonaiagents.tools.trust import EXTERNAL_TOOL_NAMES

    assert tools.FXMacroDataTools is FXMacroDataTools
    assert tools.fxmacrodata_indicator is fxm.fxmacrodata_indicator
    assert tools.fxmacrodata is fxm.fxmacrodata_indicator
    assert "fxmacrodata_indicator" in EXTERNAL_TOOL_NAMES
