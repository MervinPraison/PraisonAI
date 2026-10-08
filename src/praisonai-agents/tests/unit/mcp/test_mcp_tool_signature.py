"""MCP tool wrappers must accept any JSON Schema property name.

MCP input schemas can name a property with a Python keyword (``from``) or a
non-identifier (``max-results``), and can list required properties after
optional ones. ``inspect.Parameter`` rejects all of these, which used to abort
the whole server connection (``ValueError: 'from' is not a valid parameter
name``). The wrappers must still build, and the original argument names must
reach the server unchanged.
"""

import asyncio
import importlib
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praisonaiagents.mcp.mcp_schema_utils import build_tool_signature

# Shape of a real server's tool: optional ``from``/``to`` date range filters.
STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "from": {"type": "string", "default": "24h"},
        "to": {"type": "string", "default": "now"},
    },
}
CALL_ARGUMENTS = {"domain": "example.com", "from": "7d"}


class TestBuildToolSignature:
    def test_plain_schema_keeps_named_parameters(self):
        """Ordinary property names stay named parameters with their types and defaults."""
        sig = build_tool_signature({
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        })

        assert list(sig.parameters) == ["query", "max_results"]
        assert sig.parameters["query"].default is inspect.Parameter.empty
        assert sig.parameters["query"].annotation is str
        assert sig.parameters["max_results"].default is None
        assert sig.parameters["max_results"].annotation is int

    def test_keyword_property_is_accepted_through_kwargs(self):
        """A Python keyword (``from``) is accepted through ``**kwargs`` instead of failing."""
        sig = build_tool_signature(STATUS_SCHEMA)

        assert list(sig.parameters) == ["domain", "to", "kwargs"]
        assert sig.parameters["kwargs"].kind is inspect.Parameter.VAR_KEYWORD
        bound = sig.bind(**CALL_ARGUMENTS)
        assert bound.arguments["kwargs"] == {"from": "7d"}

    def test_non_identifier_property_is_accepted_through_kwargs(self):
        """A name that is not an identifier (``max-results``) is accepted through ``**kwargs``."""
        sig = build_tool_signature({
            "type": "object",
            "properties": {"max-results": {"type": "integer"}},
        })

        assert [p.kind for p in sig.parameters.values()] == [inspect.Parameter.VAR_KEYWORD]
        sig.bind(**{"max-results": 5})

    def test_required_property_after_optional_property(self):
        """Required properties come first even when the schema lists them after optional ones."""
        sig = build_tool_signature({
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "url": {"type": "string"},
            },
            "required": ["url"],
        })

        assert list(sig.parameters) == ["url", "limit"]

    def test_var_keyword_name_does_not_clash_with_a_property(self):
        """The ``**kwargs`` parameter is renamed when a property is already called ``kwargs``."""
        sig = build_tool_signature({
            "type": "object",
            "properties": {"kwargs": {"type": "object"}, "class": {"type": "string"}},
        })

        assert list(sig.parameters) == ["kwargs", "_kwargs"]
        assert sig.parameters["_kwargs"].kind is inspect.Parameter.VAR_KEYWORD

    @pytest.mark.parametrize(
        "schema",
        [None, {}, {"type": "object"}, {"type": "object", "properties": None}],
    )
    def test_schema_without_properties_has_no_parameters(self, schema):
        """Schemas without properties produce an empty signature."""
        assert len(build_tool_signature(schema).parameters) == 0

    def test_null_required_list_means_all_optional(self):
        """``required: null`` makes every property optional."""
        sig = build_tool_signature({
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": None,
        })

        assert sig.parameters["q"].default is None


@pytest.mark.parametrize(
    "module_name, class_name",
    [
        ("praisonaiagents.mcp.mcp_http_stream", "HTTPStreamMCPTool"),
        ("praisonaiagents.mcp.mcp_sse", "SSEMCPTool"),
        ("praisonaiagents.mcp.mcp_websocket", "WebSocketMCPTool"),
    ],
)
def test_remote_tool_forwards_keyword_named_argument(module_name, class_name):
    """SSE, HTTP-stream, and WebSocket wrappers send keyword-named arguments unchanged."""
    module = importlib.import_module(module_name)
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=SimpleNamespace(isError=False, content=[SimpleNamespace(text="ok")])
    )

    tool = getattr(module, class_name)(
        name="status",
        description="Account status",
        session=session,
        input_schema=STATUS_SCHEMA,
    )

    assert "kwargs" in inspect.signature(tool).parameters
    assert asyncio.run(tool._async_call(**CALL_ARGUMENTS)) == "ok"
    session.call_tool.assert_awaited_once_with("status", CALL_ARGUMENTS)


def test_stdio_tool_forwards_keyword_named_argument():
    """The stdio wrapper sends keyword-named arguments unchanged."""
    pytest.importorskip("mcp", reason="MCP module not installed")
    from praisonaiagents.mcp.mcp import MCP

    mcp = MCP.__new__(MCP)
    mcp.runner = MagicMock()
    mcp.runner.call_tool.return_value = "ok"
    tool = SimpleNamespace(name="status", description="Account status", inputSchema=STATUS_SCHEMA)

    wrapper = mcp._create_tool_wrapper(tool)

    assert list(inspect.signature(wrapper).parameters) == ["domain", "to", "kwargs"]
    assert wrapper(**CALL_ARGUMENTS) == "ok"
    mcp.runner.call_tool.assert_called_once_with("status", CALL_ARGUMENTS)


def test_stdio_tool_schema_exposes_non_identifier_property():
    """Callable-list path (Agent(tools=list(mcp))) must still show ``from`` to the LLM.

    The wrapper keeps ``from`` in ``**kwargs``, which signature-based schema
    builders drop. ``get_schema`` returns the server's original inputSchema so
    the model sees every property.
    """
    pytest.importorskip("mcp", reason="MCP module not installed")
    from praisonaiagents.mcp.mcp import MCP

    mcp = MCP.__new__(MCP)
    mcp.runner = MagicMock()
    tool = SimpleNamespace(name="status", description="Account status", inputSchema=STATUS_SCHEMA)

    wrapper = mcp._create_tool_wrapper(tool)

    schema = wrapper.get_schema()
    assert schema["function"]["name"] == "status"
    properties = schema["function"]["parameters"]["properties"]
    assert set(properties) == {"domain", "from", "to"}


def test_stdio_tool_positional_arguments_map_to_named_parameters():
    """Positional calls must follow the visible signature, not raw schema order.

    STATUS_SCHEMA declares ``domain``, ``from``, ``to``; ``from`` is handled via
    ``**kwargs`` so the signature is ``(domain, to, **kwargs)``. A positional
    call ``wrapper("example.com", "now")`` must send ``now`` as ``to``.
    """
    pytest.importorskip("mcp", reason="MCP module not installed")
    from praisonaiagents.mcp.mcp import MCP

    mcp = MCP.__new__(MCP)
    mcp.runner = MagicMock()
    mcp.runner.call_tool.return_value = "ok"
    tool = SimpleNamespace(name="status", description="Account status", inputSchema=STATUS_SCHEMA)

    wrapper = mcp._create_tool_wrapper(tool)

    assert wrapper("example.com", "now") == "ok"
    mcp.runner.call_tool.assert_called_once_with(
        "status", {"domain": "example.com", "to": "now"}
    )


@pytest.mark.parametrize(
    "module_name, class_name",
    [
        ("praisonaiagents.mcp.mcp_http_stream", "HTTPStreamMCPTool"),
        ("praisonaiagents.mcp.mcp_sse", "SSEMCPTool"),
        ("praisonaiagents.mcp.mcp_websocket", "WebSocketMCPTool"),
    ],
)
def test_remote_tool_call_from_worker_thread_runs_on_session_loop(module_name, class_name):
    """Agents execute tools in executor threads; the call must reach the session's loop."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    module = importlib.import_module(module_name)
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=SimpleNamespace(isError=False, content=[SimpleNamespace(text="ok")])
    )
    session_loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=session_loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        async def create_tool():  # clients create wrappers inside _async_initialize
            """Create the wrapper on the session loop, as clients do in ``_async_initialize``."""
            return getattr(module, class_name)(
                name="fetch", description="Fetch a page", session=session,
                input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
                timeout=5,
            )

        tool = asyncio.run_coroutine_threadsafe(create_tool(), session_loop).result(timeout=5)
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(tool, url="https://example.com").result(timeout=10)
    finally:
        session_loop.call_soon_threadsafe(session_loop.stop)
        loop_thread.join(timeout=5)
        session_loop.close()

    assert result == "ok"
    session.call_tool.assert_awaited_once_with("fetch", {"url": "https://example.com"})
