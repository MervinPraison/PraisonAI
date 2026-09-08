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
from urllib.parse import quote, urljoin, urlsplit

logger = logging.getLogger(__name__)

_BODY_METHODS = {"post", "put", "patch", "delete"}
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

# Keys the framework injects into a tool call rather than the model supplying
# them. ``OpenAPIOperation.__call__`` takes ``**kwargs``, which is exactly the
# signature durable execution inspects before adding an idempotency key, so on
# the free-form-body path below these must not be swept into the payload.
_FRAMEWORK_KWARGS = frozenset({
    "idempotency_key", "_idempotency_key", "run_id", "_run_id",
    "_tool_call_id", "_agent", "_task_id",
})

# Composition keywords whose subschemas contribute properties to the parent.
_COMPOSITION_KEYS = ("allOf", "oneOf", "anyOf")


def _body_properties(schema: Any) -> Dict[str, Any]:
    """Collect a body schema's properties, flattening allOf/oneOf/anyOf.

    Composition is how real specs express "this object, plus those fields", and
    such a schema carries no top-level ``properties`` at all. Reading only the
    top level therefore found nothing -- which both hid the body arguments from
    the model and, on the send side, filtered every one of them out.

    For ``oneOf``/``anyOf`` the union is taken: the caller is describing which
    arguments a tool *may* accept, and a superset is the useful answer there.
    """
    if not isinstance(schema, dict):
        return {}
    props: Dict[str, Any] = {}
    direct = schema.get("properties")
    if isinstance(direct, dict):
        props.update(direct)
    for key in _COMPOSITION_KEYS:
        for sub_schema in schema.get(key) or []:
            for name, value in _body_properties(sub_schema).items():
                props.setdefault(name, value)
    return props


def _body_required(schema: Any) -> List[str]:
    """Required body field names, flattened the same way as the properties.

    Only ``allOf`` contributes: a field required by just one branch of an
    ``oneOf`` is not required of the request as a whole.
    """
    if not isinstance(schema, dict):
        return []
    out: List[str] = list(schema.get("required") or [])
    for sub_schema in schema.get("allOf") or []:
        for name in _body_required(sub_schema):
            if name not in out:
                out.append(name)
    return out


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
                 body_param: Optional[str] = None,
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
        # Swagger 2 declares the whole request body as one named parameter
        # (``in: body``). When set, that single argument *is* the JSON body
        # rather than one property of it, and OpenAPI 3's property-spreading
        # must not apply.
        self.body_param = body_param
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
        form: Dict[str, Any] = {}
        swagger_body: Any = None
        consumed = set()

        for param in self.parameters:
            pname = param.get("name")
            if pname is None or pname not in kwargs:
                continue
            where = param.get("in")
            value = kwargs[pname]
            consumed.add(pname)
            if where == "path":
                # Percent-encode as a single path segment. A raw model-supplied
                # value like ``../../admin`` or an absolute ``https://other/``
                # would otherwise alter the path, query, fragment or host that
                # ``urljoin`` builds, sending the configured credentials
                # somewhere they were never meant to go.
                path = path.replace("{" + pname + "}",
                                    quote(str(value), safe=""))
            elif where == "query":
                query[pname] = value
            elif where == "header":
                headers[pname] = str(value)
            elif where == "body":
                # Swagger 2: this one argument is the entire JSON body.
                swagger_body = value
            elif where in ("formData", "form"):
                form[pname] = value

        if swagger_body is not None:
            body = swagger_body
        elif self.body_schema is not None:
            # Only spread the body-schema's declared properties. Copying every
            # unconsumed kwarg would leak framework-injected arguments (e.g. the
            # durable-execution ``idempotency_key`` added for ``**kwargs``
            # callables) into the request, breaking strict APIs and any schema
            # with ``additionalProperties: false``.
            # A schema that declares properties (directly or through
            # allOf/oneOf/anyOf) is the filter. A schema that declares none is
            # a free-form body -- legal, and common as bare {"type": "object"}
            # or additionalProperties: true -- and filtering against an empty
            # set would send an empty body for every such operation, which is
            # the silent-drop this filter exists to prevent.
            allowed = set(_body_properties(self.body_schema))
            for key, value in kwargs.items():
                if key in consumed or key in _FRAMEWORK_KWARGS:
                    continue
                if allowed and key not in allowed:
                    logger.debug("dropping undeclared body key %r for %s",
                                 key, self.name)
                    continue
                body[key] = value

        if self.base_url:
            url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
            # Percent-encoding above closes the *model-supplied* route to an
            # off-origin request. This closes the remaining one: a spec is
            # itself untrusted input in the "point your agent at this OpenAPI
            # URL" case, and an absolute path in the spec would otherwise
            # relocate a request that carries this toolset's credentials.
            configured, built = urlsplit(self.base_url), urlsplit(url)
            # Compare scheme as well as host: a same-host value that only
            # downgrades https:// to http:// (an absolute path from an
            # untrusted spec) would otherwise pass a host-only check and send
            # this toolset's credentials in the clear.
            if configured.netloc and (
                built.netloc != configured.netloc
                or built.scheme != configured.scheme
            ):
                configured_origin = (f"{configured.scheme}://{configured.netloc}"
                                     if configured.scheme else configured.netloc)
                built_origin = (f"{built.scheme}://{built.netloc}"
                                if built.scheme else (built.netloc or "(no host)"))
                raise ValueError(
                    f"{self.name}: refusing to send credentialed request to "
                    f"{built_origin}; configured origin is "
                    f"{configured_origin}")
        else:
            url = path
        if not urlsplit(url).netloc:
            # A relative `servers:` entry ("/v1") is valid OpenAPI and is
            # resolved against spec_url when there is one. When there is not,
            # this produced a hostless URL and every operation failed with an
            # opaque transport error instead of naming the cause.
            raise ValueError(
                f"{self.name}: no host to send to -- the spec's server URL is "
                f"relative ({self.base_url!r}) and could not be resolved. Pass "
                f"an absolute base_url= to OpenAPIToolset.")
        request: Dict[str, Any] = {"method": self.method.upper(), "url": url,
                                   "headers": headers}
        if query:
            request["params"] = query
        if body:
            request["json"] = body
        if form:
            request["data"] = form
        return request

    def __call__(self, **kwargs: Any) -> Any:
        try:
            import httpx
        except ImportError:
            return ("openapi tools need httpx: pip install httpx")
        try:
            request = self.build_request(**kwargs)
        except ValueError as exc:
            # Returned, not raised, for the same reason as the transport errors
            # below: a raising tool ends the turn.
            return f"{self.name} failed: {exc}"
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
        # Retained so a relative ``servers``/``basePath`` in a remotely loaded
        # spec can be resolved back to the origin it was fetched from.
        self._spec_url = spec_url
        self.spec = self._load(spec_dict, spec_str, spec_url)
        self.base_url = base_url or self._infer_base_url(self.spec)
        if auth and str(self.base_url).lower().startswith("http://"):
            # Refuse to attach credentials to a cleartext endpoint: bearer
            # tokens, API keys and basic-auth values would travel in the clear.
            raise ValueError(
                "OpenAPIToolset refuses to send auth over http:// "
                f"(base_url={self.base_url!r}); use https or pass base_url= "
                "with an https endpoint.")
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

    def _infer_base_url(self, spec: Dict[str, Any]) -> str:
        servers = spec.get("servers")
        if isinstance(servers, list) and servers:
            first = servers[0]
            if isinstance(first, dict) and first.get("url"):
                url = str(first["url"])
                # A spec loaded from a URL may declare a relative server such
                # as ``/v1``; resolve it against the origin it was fetched from
                # so generated operations do not produce hostless URLs.
                if url.startswith("/") and self._spec_url:
                    return urljoin(self._spec_url, url)
                return url
        # Swagger 2.0
        host, base = spec.get("host"), spec.get("basePath", "")
        if host:
            schemes = spec.get("schemes") or ["https"]
            # Prefer HTTPS whenever the spec offers it rather than blindly
            # taking the first scheme, so authenticated requests are not sent
            # in cleartext when a secure endpoint exists.
            scheme = "https" if "https" in schemes else schemes[0]
            return f"{scheme}://{host}{base}"
        # Swagger 2 may omit host but still be reachable at the origin it was
        # fetched from.
        if self._spec_url and base:
            return urljoin(self._spec_url, base)
        return ""

    def _body_info(self, operation: Dict[str, Any],
                   parameters: List[Dict[str, Any]]):
        """Resolve the JSON body schema and its Swagger-2 parameter name.

        OpenAPI 3 carries the body under ``requestBody.content`` and spreads
        its properties as arguments. Swagger 2 declares it as a single
        ``in: body`` parameter whose ``schema`` is the whole body. Returns
        ``(body_schema, body_param_name)`` where ``body_param_name`` is set
        only for the Swagger 2 form.
        """
        body = operation.get("requestBody") or {}
        content = (body.get("content") or {}).get("application/json") or {}
        if content:
            schema = _resolve_ref(content.get("schema") or {}, self.spec)
            return (schema if isinstance(schema, dict) else None), None
        for param in parameters:
            if param.get("in") == "body":
                schema = _resolve_ref(param.get("schema") or {}, self.spec)
                return (schema if isinstance(schema, dict) else None), param.get("name")
        return None, None

    def _input_schema(self, parameters: List[Dict[str, Any]],
                      body_schema: Optional[Dict[str, Any]],
                      body_param: Optional[str]) -> Dict[str, Any]:
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for param in parameters:
            pname = param.get("name")
            if not pname or param.get("in") == "body":
                continue
            schema = _resolve_ref(param.get("schema") or {"type": "string"}, self.spec)
            if param.get("description"):
                schema = {**schema, "description": param["description"]}
            properties[pname] = schema
            if param.get("required"):
                required.append(pname)

        if body_param:
            # Swagger 2: expose the body as one named object argument.
            properties.setdefault(body_param, body_schema or {"type": "object"})
        elif isinstance(body_schema, dict):
            for key, value in _body_properties(body_schema).items():
                properties.setdefault(key, value)
            required.extend(r for r in _body_required(body_schema)
                            if r not in required and r in properties)

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
                body_schema, body_param = self._body_info(operation, parameters)
                tools.append(OpenAPIOperation(
                    name=name,
                    description=(operation.get("summary")
                                 or operation.get("description") or ""),
                    method=method, path=path, base_url=self.base_url,
                    parameters=parameters,
                    body_schema=body_schema,
                    body_param=body_param,
                    input_schema=self._input_schema(
                        parameters, body_schema, body_param),
                    auth=self.auth, header_provider=self.header_provider,
                    timeout=self.timeout))
        return tools


__all__ = ["OpenAPIToolset", "OpenAPIOperation"]
