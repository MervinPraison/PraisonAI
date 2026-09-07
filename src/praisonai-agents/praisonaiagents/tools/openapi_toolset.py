"""Turn an OpenAPI/Swagger spec into callable agent tools.

PraisonAI emits OpenAPI specs in several places (``recipe/serve.py``,
``app/agentos.py``, ``ui/agui``, ``ui/a2a``) and consumed one nowhere, so
pointing an agent at an existing REST API meant hand-writing a function per
endpoint. A whole spec is now one line:

    from praisonaiagents.tools.openapi_toolset import OpenAPIToolset

    toolset = OpenAPIToolset(spec_url="https://api.example.com/openapi.json",
                             auth={"type": "bearer", "token": os.environ["API_TOKEN"]})
    agent = Agent(name="ops", tools=toolset.get_tools())

There is an existing workaround -- ``MCP("npx -y @ivotoby/openapi-mcp-server
...")`` fronts a spec as an MCP server -- so this is not a capability that was
unreachable. What it costs is an extra process, an npx dependency, and no
reuse of PraisonAI's own tool plumbing. Everything here routes through the
same helpers the MCP tools use, so a generated tool is indistinguishable from
any other to the Agent.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

_BODY_METHODS = {"post", "put", "patch", "delete"}
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _resolve_ref(schema: Any, root: Dict[str, Any], _seen: Optional[set] = None) -> Any:
    """Expand local ``$ref`` pointers against the document.

    Only local refs are followed: a remote ``$ref`` would mean fetching an
    arbitrary URL while merely *describing* a tool, which is a surprising
    thing for spec parsing to do. Cycles are broken rather than recursed --
    a self-referential schema is common in real specs and must not hang.
    """
    if not isinstance(schema, dict):
        return schema
    seen = _seen or set()
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        if ref in seen:
            return {"type": "object"}
        target: Any = root
        for part in ref[2:].split("/"):
            if not isinstance(target, dict) or part not in target:
                return {"type": "object"}
            target = target[part]
        return _resolve_ref(target, root, seen | {ref})
    out: Dict[str, Any] = {}
    for key, value in schema.items():
        if key == "$ref":
            continue
        if isinstance(value, dict):
            out[key] = _resolve_ref(value, root, seen)
        elif isinstance(value, list):
            out[key] = [_resolve_ref(v, root, seen) if isinstance(v, dict) else v
                        for v in value]
        else:
            out[key] = value
    return out


def _operation_name(method: str, path: str, operation: Dict[str, Any]) -> str:
    """A stable, model-friendly tool name."""
    raw = operation.get("operationId")
    if raw:
        name = "".join(c if (c.isalnum() or c == "_") else "_" for c in str(raw))
    else:
        # No operationId: build one from the verb and path so the name is
        # still deterministic across runs rather than positional.
        cleaned = path.strip("/").replace("{", "").replace("}", "")
        name = method + "_" + "".join(c if c.isalnum() else "_" for c in cleaned)
    name = "_".join(filter(None, name.split("_")))
    return name or f"{method}_operation"


class OpenAPIOperation:
    """One spec operation, callable like any other PraisonAI tool.

    Shaped like ``mcp_sse.SSEMCPTool``: ``__name__``/``__qualname__``/``__doc__``
    are what the Agent inspects to recognise a tool, so a generated operation
    needs no Agent-side change.
    """

    def __init__(self, *, name: str, description: str, method: str, path: str,
                 base_url: str, parameters: List[Dict[str, Any]],
                 body_schema: Optional[Dict[str, Any]],
                 input_schema: Dict[str, Any],
                 auth: Optional[Dict[str, Any]] = None,
                 header_provider: Optional[Callable[[], Dict[str, str]]] = None,
                 timeout: int = 30):
        self.name = name
        self.__name__ = name
        self.__qualname__ = name
        self.__doc__ = description or f"{method.upper()} {path}"
        self.description = self.__doc__
        self.method = method.lower()
        self.path = path
        self.base_url = base_url
        self.parameters = parameters
        self.body_schema = body_schema
        self.input_schema = input_schema
        self.auth = auth or {}
        self.header_provider = header_provider
        self.timeout = timeout

    # -- request construction ------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        kind = str(self.auth.get("type", "")).lower()
        if kind == "bearer" and self.auth.get("token"):
            headers["Authorization"] = f"Bearer {self.auth['token']}"
        elif kind == "api_key" and self.auth.get("key"):
            headers[self.auth.get("name") or "X-API-Key"] = self.auth["key"]
        elif kind == "basic" and self.auth.get("value"):
            headers["Authorization"] = f"Basic {self.auth['value']}"
        if self.header_provider:
            try:
                headers.update(self.header_provider() or {})
            except Exception:  # noqa: BLE001 - a bad provider must not kill the call
                logger.warning("header_provider raised; continuing without it",
                               exc_info=True)
        return headers

    def build_request(self, **kwargs: Any) -> Dict[str, Any]:
        """Bind arguments to path, query, header and body.

        Separated from ``__call__`` so the binding can be asserted in a test
        without a transport: the mapping from arguments to an HTTP request is
        the part that carries the bugs.
        """
        path = self.path
        query: Dict[str, Any] = {}
        headers = self._headers()
        body: Dict[str, Any] = {}
        consumed = set()

        for param in self.parameters:
            pname = param.get("name")
            if pname is None or pname not in kwargs:
                continue
            where = param.get("in")
            value = kwargs[pname]
            consumed.add(pname)
            if where == "path":
                path = path.replace("{" + pname + "}", str(value))
            elif where == "query":
                query[pname] = value
            elif where == "header":
                headers[pname] = str(value)

        if self.body_schema is not None:
            for key, value in kwargs.items():
                if key not in consumed:
                    body[key] = value

        url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/")) \
            if self.base_url else path
        request: Dict[str, Any] = {"method": self.method.upper(), "url": url,
                                   "headers": headers}
        if query:
            request["params"] = query
        if body:
            request["json"] = body
        return request

    def __call__(self, **kwargs: Any) -> Any:
        try:
            import httpx
        except ImportError:
            return ("openapi tools need httpx: pip install httpx")
        request = self.build_request(**kwargs)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(**request)
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError:
                    return response.text
        except Exception as exc:  # noqa: BLE001 - the model must see the failure
            # Returned rather than raised: a tool that raises ends the turn,
            # while a returned error lets the model retry or explain.
            return f"{self.name} failed: {exc}"

    def to_openai_tool(self) -> Dict[str, Any]:
        """The function-calling dict, via the same helper the MCP tools use."""
        from ..mcp.mcp_schema_utils import build_openai_tool_dict
        return build_openai_tool_dict(self.name, self.description, self.input_schema)


class OpenAPIToolset:
    """Every operation in a spec, as agent tools."""

    def __init__(self, *, spec_dict: Optional[Dict[str, Any]] = None,
                 spec_str: Optional[str] = None,
                 spec_url: Optional[str] = None,
                 base_url: Optional[str] = None,
                 auth: Optional[Dict[str, Any]] = None,
                 tool_filter: Optional[Callable[[str, str, str], bool]] = None,
                 tool_name_prefix: Optional[str] = None,
                 header_provider: Optional[Callable[[], Dict[str, str]]] = None,
                 timeout: int = 30):
        if spec_dict is None and spec_str is None and spec_url is None:
            raise ValueError(
                "OpenAPIToolset needs one of spec_dict=, spec_str= or spec_url=")
        self.spec = self._load(spec_dict, spec_str, spec_url)
        self.base_url = base_url or self._infer_base_url(self.spec)
        self.auth = auth
        self.tool_filter = tool_filter
        self.tool_name_prefix = tool_name_prefix
        self.header_provider = header_provider
        self.timeout = timeout

    @staticmethod
    def _load(spec_dict, spec_str, spec_url) -> Dict[str, Any]:
        if spec_dict is not None:
            return spec_dict
        if spec_str is not None:
            text = spec_str
        else:
            import httpx
            with httpx.Client(timeout=30) as client:
                response = client.get(spec_url)
                response.raise_for_status()
                text = response.text
        try:
            return json.loads(text)
        except ValueError:
            # A YAML spec is as common as a JSON one; PyYAML is already a
            # dependency, but say so plainly if it is somehow absent.
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise ValueError(
                    "spec is not JSON and PyYAML is unavailable to parse it") from exc
            return yaml.safe_load(text)

    @staticmethod
    def _infer_base_url(spec: Dict[str, Any]) -> str:
        servers = spec.get("servers")
        if isinstance(servers, list) and servers:
            first = servers[0]
            if isinstance(first, dict) and first.get("url"):
                return str(first["url"])
        # Swagger 2.0
        host, base = spec.get("host"), spec.get("basePath", "")
        if host:
            schemes = spec.get("schemes") or ["https"]
            return f"{schemes[0]}://{host}{base}"
        return ""

    def _input_schema(self, operation: Dict[str, Any],
                      parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for param in parameters:
            pname = param.get("name")
            if not pname:
                continue
            schema = _resolve_ref(param.get("schema") or {"type": "string"}, self.spec)
            if param.get("description"):
                schema = {**schema, "description": param["description"]}
            properties[pname] = schema
            if param.get("required"):
                required.append(pname)

        body = operation.get("requestBody") or {}
        content = (body.get("content") or {}).get("application/json") or {}
        body_schema = _resolve_ref(content.get("schema") or {}, self.spec) if content else None
        if isinstance(body_schema, dict) and body_schema.get("properties"):
            for key, value in body_schema["properties"].items():
                properties.setdefault(key, value)
            required.extend(r for r in (body_schema.get("required") or [])
                            if r not in required)

        schema: Dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def get_tools(self) -> List[OpenAPIOperation]:
        """One callable per operation, ready for ``Agent(tools=...)``."""
        tools: List[OpenAPIOperation] = []
        paths = self.spec.get("paths") or {}
        for path, item in paths.items():
            if not isinstance(item, dict):
                continue
            shared = item.get("parameters") or []
            for method, operation in item.items():
                if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                    continue
                name = _operation_name(method, path, operation)
                if self.tool_filter and not self.tool_filter(name, method, path):
                    continue
                if self.tool_name_prefix:
                    name = f"{self.tool_name_prefix}{name}"
                parameters = [_resolve_ref(p, self.spec)
                              for p in (shared + (operation.get("parameters") or []))]
                body = operation.get("requestBody")
                tools.append(OpenAPIOperation(
                    name=name,
                    description=(operation.get("summary")
                                 or operation.get("description") or ""),
                    method=method, path=path, base_url=self.base_url,
                    parameters=parameters,
                    body_schema={} if body else None,
                    input_schema=self._input_schema(operation, parameters),
                    auth=self.auth, header_provider=self.header_provider,
                    timeout=self.timeout))
        return tools


__all__ = ["OpenAPIToolset", "OpenAPIOperation"]
