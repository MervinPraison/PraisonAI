"""
Passthrough Capabilities Module

Provides generic API passthrough functionality for provider-specific endpoints.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict
from urllib.parse import urlparse
import asyncio
import ipaddress
import threading


# Shared HTTP clients for the httpx fallback path (used when litellm's
# passthrough route is unavailable). Reused across calls so the hot passthrough
# fallback shares a keep-alive connection pool instead of opening + tearing down
# a socket per agent call. Timeout is applied per-request, so a single client
# safely serves callers with different ``timeout`` values.
_sync_client: Any = None
# One async client per owning event loop, keyed by ``id(loop)``. ``httpx``
# binds a client's connection pool to the loop that first uses it, so sharing a
# single module-level slot across loops both (a) leaks the previous loop's pool
# (it is dropped, never ``aclose()``d) and (b) crashes callers that resume on
# their own loop but find the slot swapped to another. Keying by loop keeps each
# loop's client isolated and lets us close each one from within its own loop.
_async_clients: Dict[int, Any] = {}
_client_lock = threading.Lock()


def _get_sync_client() -> Any:
    """Return the shared sync httpx client, constructing it lazily."""
    global _sync_client
    if _sync_client is None:
        with _client_lock:
            if _sync_client is None:
                import httpx
                _sync_client = httpx.Client()
    return _sync_client


def _get_async_client() -> Any:
    """Return the async httpx client for the *current* event loop.

    The client is cached per running loop so its connection pool is never reused
    from a different loop (which raises loop-closed / wrong-loop errors) and is
    never silently replaced (which would leak the previous loop's sockets). Each
    loop's client is drained via :func:`aclose_clients` from within that loop.
    """
    import httpx

    loop = asyncio.get_running_loop()
    key = id(loop)
    with _client_lock:
        client = _async_clients.get(key)
        if client is None:
            client = httpx.AsyncClient()
            _async_clients[key] = client
        return client


def close_clients() -> None:
    """Close the cached sync client and drop the per-loop async clients.

    Provided as an explicit shutdown hook for long-lived hosts that want to
    release the pooled sockets deterministically. An ``AsyncClient`` cannot be
    awaited from this sync helper, so the per-loop async clients are dropped
    (and rebuilt per-loop on next use); the sync client is closed here. Prefer
    :func:`aclose_clients` from within an event loop to close the async pool
    cleanly.
    """
    global _sync_client
    with _client_lock:
        if _sync_client is not None:
            try:
                _sync_client.close()
            finally:
                _sync_client = None
        _async_clients.clear()


async def aclose_clients() -> None:
    """Await-close the current loop's async client and the shared sync one.

    Only the running loop's client can be awaited here; clients owned by other
    loops must be closed from within their own loop (call this on each loop
    before it tears down), so they are left in place rather than dropped.
    """
    global _sync_client
    try:
        key = id(asyncio.get_running_loop())
    except RuntimeError:
        key = None
    client = None
    with _client_lock:
        if key is not None:
            client = _async_clients.pop(key, None)
        if _sync_client is not None:
            try:
                _sync_client.close()
            finally:
                _sync_client = None
    if client is not None:
        await client.aclose()


@dataclass
class PassthroughResult:
    """Result from passthrough API call."""
    data: Any
    status_code: int = 200
    headers: Optional[Dict[str, str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _validate_api_base(url: str) -> str:
    """Validate api_base URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(
            f"Invalid URL scheme '{parsed.scheme}'. Only http and https are allowed."
        )
    hostname = parsed.hostname or ''
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(
                f"URL points to a private/internal address: {hostname}"
            )
    except ValueError as exc:
        if 'private' in str(exc) or 'internal' in str(exc):
            raise
        # hostname is a domain name, not an IP — that's fine
    return url


def passthrough(
    endpoint: str,
    method: str = "POST",
    model: Optional[str] = None,
    custom_llm_provider: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> PassthroughResult:
    """
    Make a passthrough API call to a provider endpoint.
    
    Args:
        endpoint: The endpoint path (e.g., "/v1/custom/endpoint")
        method: HTTP method ("GET", "POST", "PUT", "DELETE")
        model: Optional model name for routing
        custom_llm_provider: Provider name
        data: Form data
        json_data: JSON body data
        headers: Additional headers
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        PassthroughResult with response data
        
    Example:
        >>> result = passthrough(
        ...     "/v1/custom/endpoint",
        ...     method="POST",
        ...     json_data={"key": "value"},
        ...     custom_llm_provider="openai"
        ... )
        >>> print(result.data)
    """
    import litellm
    
    call_kwargs = {
        'endpoint': endpoint,
        'method': method,
        'timeout': timeout,
    }
    
    if model:
        call_kwargs['model'] = model
    if custom_llm_provider:
        call_kwargs['custom_llm_provider'] = custom_llm_provider
    if data:
        call_kwargs['data'] = data
    if json_data:
        call_kwargs['json'] = json_data
    if headers:
        call_kwargs['request_headers'] = headers
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    # Use passthrough route if available
    try:
        response = litellm.llm_passthrough_route(**call_kwargs)
        
        return PassthroughResult(
            data=response.json() if hasattr(response, 'json') else response,
            status_code=getattr(response, 'status_code', 200),
            headers=dict(response.headers) if hasattr(response, 'headers') else None,
            metadata=metadata or {},
        )
    except AttributeError:
        # Fallback to a shared httpx client if the passthrough route is missing.
        url = f"{_validate_api_base(api_base) if api_base else 'https://api.openai.com'}{endpoint}"
        request_headers = headers or {}
        if api_key:
            request_headers['Authorization'] = f"Bearer {api_key}"
        
        response = _get_sync_client().request(
            method=method,
            url=url,
            headers=request_headers,
            json=json_data,
            data=data,
            timeout=timeout,
        )
        
        return PassthroughResult(
            data=response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
            status_code=response.status_code,
            headers=dict(response.headers),
            metadata=metadata or {},
        )


async def apassthrough(
    endpoint: str,
    method: str = "POST",
    model: Optional[str] = None,
    custom_llm_provider: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> PassthroughResult:
    """
    Async: Make a passthrough API call to a provider endpoint.
    
    See passthrough() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'endpoint': endpoint,
        'method': method,
        'timeout': timeout,
    }
    
    if model:
        call_kwargs['model'] = model
    if custom_llm_provider:
        call_kwargs['custom_llm_provider'] = custom_llm_provider
    if data:
        call_kwargs['data'] = data
    if json_data:
        call_kwargs['json'] = json_data
    if headers:
        call_kwargs['request_headers'] = headers
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    try:
        response = await litellm.allm_passthrough_route(**call_kwargs)
        
        return PassthroughResult(
            data=response.json() if hasattr(response, 'json') else response,
            status_code=getattr(response, 'status_code', 200),
            headers=dict(response.headers) if hasattr(response, 'headers') else None,
            metadata=metadata or {},
        )
    except AttributeError:
        url = f"{_validate_api_base(api_base) if api_base else 'https://api.openai.com'}{endpoint}"
        request_headers = headers or {}
        if api_key:
            request_headers['Authorization'] = f"Bearer {api_key}"
        
        response = await _get_async_client().request(
            method=method,
            url=url,
            headers=request_headers,
            json=json_data,
            data=data,
            timeout=timeout,
        )
        
        return PassthroughResult(
            data=response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
            status_code=response.status_code,
            headers=dict(response.headers),
            metadata=metadata or {},
        )
