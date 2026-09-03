import os
import json
import base64
import hmac
import secrets
import asyncio
import argparse
import logging
import importlib.util
import threading
import time
from typing import Optional
from collections import defaultdict

# Heavy, optional dependencies (websockets, fastapi, twilio, uvicorn, pyngrok,
# rich) are imported lazily inside the functions that need them. Importing this
# module must stay cheap: ``import praisonai.api.call`` (reachable from unrelated
# code paths) should not pay the transitive cost of the voice/serve stack or
# fail on minimal containers where those native deps are absent.


def _maybe_load_dotenv() -> None:
    """Load a ``.env`` file only when explicitly opted in.

    Importing a library should never mutate ``os.environ``. Loading the
    ``.env`` at import time surprises callers who deliberately unset variables
    and makes test isolation harder. Opt in with
    ``PRAISONAI_CALL_LOAD_DOTENV=true`` (or run the ``praisonai call`` CLI which
    enables it explicitly).
    """
    if os.getenv("PRAISONAI_CALL_LOAD_DOTENV", "").lower() == "true":
        from dotenv import load_dotenv
        load_dotenv()


_maybe_load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # requires OpenAI Realtime API Access
PORT = int(os.getenv('PORT', 8090))
NGROK_AUTH_TOKEN = os.getenv('NGROK_AUTH_TOKEN')
PUBLIC = os.getenv('PUBLIC', 'false').lower() == 'true'


def _resolve_realtime_endpoint():
    """Resolve the realtime WebSocket URL + auth headers.

    Defaults to OpenAI so existing users with only ``OPENAI_API_KEY`` set keep
    working unchanged. Operators running Azure / a self-hosted realtime-capable
    gateway can point the voice path elsewhere without editing this module via:
      - ``PRAISONAI_REALTIME_URL``    full ``wss://...`` URL (takes precedence)
      - ``PRAISONAI_REALTIME_MODEL``  model for the default OpenAI URL
      - ``PRAISONAI_REALTIME_API_KEY`` bearer key (falls back to OPENAI_API_KEY)
    """
    explicit_url = os.getenv('PRAISONAI_REALTIME_URL')
    api_key = os.getenv('PRAISONAI_REALTIME_API_KEY') or OPENAI_API_KEY
    if explicit_url:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        if "openai.com" in explicit_url:
            headers["OpenAI-Beta"] = "realtime=v1"
        return explicit_url, headers

    model = os.getenv(
        'PRAISONAI_REALTIME_MODEL', 'gpt-4o-realtime-preview-2024-10-01'
    )
    return (
        f"wss://api.openai.com/v1/realtime?model={model}",
        {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        },
    )


SYSTEM_MESSAGE = (
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "Keep your responses short and to the point. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
    "Start your conversation by saying 'Hi! I'm Praison AI. How can I help you today?'"
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]

# Security and Rate Limiting
CALL_SERVER_TOKEN = os.getenv('CALL_SERVER_TOKEN')
MAX_CONCURRENT_CONNECTIONS = int(os.getenv('MAX_CONCURRENT_CONNECTIONS', '5'))
MAX_REQUESTS_PER_WINDOW = int(os.getenv('MAX_REQUESTS_PER_WINDOW', '100'))
RATE_LIMIT_WINDOW = 3600

active_connections = 0
client_ips = defaultdict(list)

# Guard the shared, async-mutated counters so concurrent WebSocket handlers
# can't over-commit MAX_CONCURRENT_CONNECTIONS / MAX_REQUESTS_PER_WINDOW via a
# check-then-mutate TOCTOU across ``await`` points.
_conn_lock = asyncio.Lock()
_ips_lock = asyncio.Lock()

# One-shot, short-lived session tokens handed to the Twilio media-stream client
# so the shared server secret is never embedded in a URL (which leaks into
# access logs / referrers / history).
_STREAM_SESSION_TTL = 60  # seconds


class CallAppState:
    """Per-app tools registry + one-shot session-token store.

    Replaces the previous module-level ``tools`` / ``_pending_stream_sessions``
    globals so co-hosted / multi-tenant ``build_call_app()`` instances in one
    process never share a tool schema or cross-consume each other's stream
    tokens. FastAPI hands this to handlers via ``request.app.state`` /
    ``websocket.app.state``.
    """

    __slots__ = ("tools", "pending_sessions", "_lock")

    def __init__(self):
        self.tools: list = []
        self.pending_sessions: "dict[str, float]" = {}
        self._lock = threading.Lock()

    def mint_stream_token(self) -> str:
        """Create a single-use, TTL-bound token for the media-stream handshake."""
        now = time.time()
        token = secrets.token_urlsafe(32)
        with self._lock:
            # Opportunistically drop expired tokens so the map can't grow unbounded.
            self.pending_sessions = {
                t: exp for t, exp in self.pending_sessions.items() if exp >= now
            }
            self.pending_sessions[token] = now + _STREAM_SESSION_TTL
        return token

    def consume_stream_token(self, token: str) -> bool:
        """Validate and consume a one-shot stream-session token (constant-time)."""
        if not token:
            return False
        now = time.time()
        with self._lock:
            for candidate, expiry in list(self.pending_sessions.items()):
                if expiry < now:
                    self.pending_sessions.pop(candidate, None)
                    continue
                if hmac.compare_digest(candidate, token):
                    self.pending_sessions.pop(candidate, None)
                    return True
        return False


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def _configured_public_base() -> Optional[str]:
    """``ws(s)://`` base for outbound Twilio media-stream URLs.

    Set via ``PRAISONAI_CALL_PUBLIC_BASE`` (e.g. ``wss://praison.example``).
    Never fall back to ``request.url.hostname`` — that is derived from the
    client-supplied ``Host`` header and would let an authenticated caller
    redirect Twilio's live media leg to an arbitrary host (SSRF / call-audio
    exfiltration). Mirrors ``_configured_bind_host`` in ``agent_invoke.py``:
    externally-visible URLs come from config, never a request header.
    """
    return os.getenv("PRAISONAI_CALL_PUBLIC_BASE")


def _validate_public_base(base: Optional[str]) -> Optional[str]:
    """Return an error string if ``base`` is not a safe media-stream base URL.

    A prefix check alone is insufficient: a value like ``ws://`` has no host
    (Twilio cannot connect) and a cleartext ``ws://`` to a non-local host sends
    the live audio *and* the one-shot session token over an unencrypted
    transport. Require a structurally valid ``wss://`` URL with a host; permit
    cleartext ``ws://`` only for localhost (dev / tunnelled setups).

    Returns ``None`` when the base is acceptable.
    """
    if not base:
        return "unset"
    from urllib.parse import urlparse
    parsed = urlparse(base)
    if parsed.scheme not in ("ws", "wss"):
        return "PRAISONAI_CALL_PUBLIC_BASE must be a ws:// or wss:// URL"
    if not parsed.hostname:
        return "PRAISONAI_CALL_PUBLIC_BASE must include a host"
    if parsed.scheme == "ws" and parsed.hostname not in _LOCAL_HOSTS:
        return (
            "PRAISONAI_CALL_PUBLIC_BASE must use wss:// for non-local hosts; "
            "cleartext ws:// would expose live audio and the session token"
        )
    return None


def _tokens_match(provided: Optional[str], expected: Optional[str]) -> bool:
    """Constant-time token comparison to avoid a timing side channel."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)


def _refresh_env_globals() -> None:
    """Re-read env-derived config into module globals.

    These globals are captured once at import. When ``.env`` is loaded later
    (e.g. explicitly in ``main()``), the request-time handlers would otherwise
    keep reading the stale import-time values. Refreshing them keeps a
    ``.env``-only ``OPENAI_API_KEY`` / ``CALL_SERVER_TOKEN`` / rate-limit
    working, matching the pre-existing import-time ``load_dotenv`` behaviour.
    """
    global OPENAI_API_KEY, PORT, NGROK_AUTH_TOKEN, PUBLIC
    global CALL_SERVER_TOKEN, MAX_CONCURRENT_CONNECTIONS, MAX_REQUESTS_PER_WINDOW
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    PORT = int(os.getenv('PORT', 8090))
    NGROK_AUTH_TOKEN = os.getenv('NGROK_AUTH_TOKEN')
    PUBLIC = os.getenv('PUBLIC', 'false').lower() == 'true'
    CALL_SERVER_TOKEN = os.getenv('CALL_SERVER_TOKEN')
    MAX_CONCURRENT_CONNECTIONS = int(os.getenv('MAX_CONCURRENT_CONNECTIONS', '5'))
    MAX_REQUESTS_PER_WINDOW = int(os.getenv('MAX_REQUESTS_PER_WINDOW', '100'))
    # The included n8n invoke router now live-reads CALL_SERVER_TOKEN from the
    # environment per request (agent_invoke._call_server_token), so no
    # cross-module reach-in is needed to keep its auth consistent.


# Set up logging
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger.handlers.clear()

def import_tools_from_file(file_path):
    """Import tools from file with PRAISONAI_ALLOW_LOCAL_TOOLS opt-in.
    
    This function is reachable from network input via API requests.
    Additional security: only allow files under the current working directory.
    """
    from .._safe_loader import load_user_module_strict, LocalToolsDisabled
    try:
        custom_tools_module = load_user_module_strict(file_path, name="custom_tools")
        logger.debug(f"Imported tools from {file_path}")
        return custom_tools_module
    except LocalToolsDisabled as e:
        logger.warning(f"Tools loading disabled: {e}")
        raise ValueError("Local tools loading disabled. Set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable.")
    except FileNotFoundError as e:
        logger.warning(f"Tools file not found: {e}")
        raise ValueError(f"Tools file not found: {file_path}")
    except Exception as e:
        logger.error("Failed to import tools from %s", file_path, exc_info=True)
        raise ValueError(f"Failed to import tools from {file_path}") from e


def _load_local_tools_into(state):
    """Load ``./tools.py`` into ``state.tools``, if opted in.

    Runs user code, so it is gated behind ``PRAISONAI_ALLOW_LOCAL_TOOLS=true``
    and only invoked by a server entry point (``build_call_app``/``main``) — never
    at import time. Importing ``praisonai.api.call`` therefore has no filesystem
    scan and never executes a neighbouring ``tools.py``.

    Idempotent: ``state.tools`` is rebuilt from scratch on each call. Building
    the app more than once in a process (e.g. two
    ``build_call_app(load_local_tools=True)`` calls) does not accumulate
    duplicate tool definitions, and — because each app owns its own ``state`` —
    a second build no longer wipes an already-running app's tool schema.
    """
    tools_path = os.path.join(os.getcwd(), 'tools.py')
    logger.debug(f"Tools path: {tools_path}")
    try:
        if os.environ.get("PRAISONAI_ALLOW_LOCAL_TOOLS", "").lower() != "true":
            logger.debug("Local tools loading disabled. Set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable.")
            custom_tools_module = None
        elif os.path.exists(tools_path):
            custom_tools_module = import_tools_from_file(tools_path)
            logger.debug("Successfully imported custom tools from root tools.py")
        else:
            logger.debug("No custom tools.py file found in the root directory")
            custom_tools_module = None

        if custom_tools_module:
            # Rebuild this app's registry from scratch so a re-load replaces
            # rather than appends.
            state.tools.clear()
            if hasattr(custom_tools_module, 'tools') and isinstance(custom_tools_module.tools, list):
                state.tools.extend(custom_tools_module.tools)
            else:
                for name, obj in custom_tools_module.__dict__.items():
                    if callable(obj) and not name.startswith("__"):
                        tool_definition = getattr(obj, 'definition', None)
                        if tool_definition:
                            state.tools.append(tool_definition)
    except Exception as e:
        logger.warning(f"Error importing custom tools: {str(e)}. Continuing without custom tools.")


def build_call_app(*, load_local_tools: bool = False):
    """Build a fresh FastAPI app with the call routes registered.

    Heavy deps (FastAPI, the agent-invoke router) are imported here, not at
    module import time. Each app owns its own :class:`CallAppState` (tools +
    pending stream tokens) hung off ``app.state.call_state`` so co-hosted apps
    never share tool schemas or cross-consume each other's session tokens. When
    ``load_local_tools`` is true and the env opt-in is set, ``./tools.py`` is
    loaded into this app's registry.
    """
    from fastapi import FastAPI

    app = FastAPI()
    state = CallAppState()
    app.state.call_state = state

    try:
        from .agent_invoke import router as agent_invoke_router
        app.include_router(agent_invoke_router)
        logger.debug("Agent invoke router added for n8n integration")
    except ImportError as e:
        logger.warning(f"Could not load agent invoke router: {e}")

    _register_routes(app)

    if load_local_tools:
        _load_local_tools_into(state)

    return app


_app = None


def __getattr__(name):
    """Lazily construct the module-level ``app`` on first access.

    Preserves the ``praisonai.api.call.app`` attribute for third parties that
    import the name directly, without building a FastAPI app (and pulling its
    transitive deps) merely because the module was imported.
    """
    if name == "app":
        global _app
        if _app is None:
            _app = build_call_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _register_routes(app):
    """Register the voice-call HTTP/WebSocket routes on ``app``.

    Handlers are defined at module scope (below) and attached here so the app is
    built lazily by :func:`build_call_app` without any import-time app object.

    The handlers are annotation-free at module scope to keep ``import
    praisonai.api.call`` free of a top-level ``fastapi`` dependency. FastAPI
    resolves framework objects (``Request``/``WebSocket``) by *annotation*, not
    by parameter name, so the real classes are stamped onto the handlers here —
    at build time, where ``fastapi`` is already imported — before registration.
    Without this, an unannotated ``request`` parameter is treated as a required
    query parameter and the ``/`` route 422s.
    """
    from fastapi import Request, WebSocket
    from fastapi.responses import HTMLResponse

    handle_incoming_call.__annotations__["request"] = Request
    handle_media_stream.__annotations__["websocket"] = WebSocket

    app.add_api_route(
        "/status", index_page, methods=["GET"], response_class=HTMLResponse
    )
    app.add_api_route("/", handle_incoming_call, methods=["GET", "POST"])
    app.add_api_websocket_route("/media-stream", handle_media_stream)


async def index_page():
    return """
    <html>
        <head>
            <title>Praison AI Call Server</title>
        </head>
        <body>
            <h1>Praison AI Call Server is running!</h1>
        </body>
    </html>
    """


async def handle_incoming_call(request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    from fastapi import HTTPException, status
    from fastapi.responses import HTMLResponse
    from twilio.twiml.voice_response import VoiceResponse, Connect

    if not CALL_SERVER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CALL_SERVER_TOKEN is not configured",
        )
    token = request.query_params.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ")[1]
        elif auth.startswith("Basic "):
            try:
                import base64
                decoded = base64.b64decode(auth[6:]).decode("utf-8")
                if ":" in decoded:
                    token = decoded.split(":", 1)[1]
                else:
                    token = decoded
            except Exception:
                pass
    if not _tokens_match(token, CALL_SERVER_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    # Build the outbound stream URL from server config, NEVER from
    # ``request.url.hostname`` (the client-controlled Host header). Otherwise an
    # authenticated caller could point Twilio's live media leg at an arbitrary
    # host and exfiltrate/inject call audio.
    base = _configured_public_base()
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "PRAISONAI_CALL_PUBLIC_BASE is not configured; refusing to "
                "derive the media-stream URL from the client Host header."
            ),
        )
    validation_error = _validate_public_base(base)
    if validation_error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=validation_error,
        )

    response = VoiceResponse()
    response.say("")
    response.pause(length=1)
    # response.say("")
    connect = Connect()

    # Never embed the shared server secret in the stream URL — a query-string
    # token leaks into intermediary access logs, referrers and history. Mint a
    # one-shot, TTL-bound session token the media-stream handshake validates and
    # consumes exactly once, scoped to this app's state.
    session_token = request.app.state.call_state.mint_stream_token()
    stream_url = f"{base.rstrip('/')}/media-stream?session={session_token}"

    connect.stream(url=stream_url)
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

async def handle_media_stream(websocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    import websockets
    from fastapi.websockets import WebSocketDisconnect

    global active_connections
    
    # 1. Authentication — accept a one-shot, per-connection session token
    #    (from the ``session`` query param minted by the incoming-call handler,
    #    or an ``x-call-token`` header). The shared CALL_SERVER_TOKEN is never
    #    carried in the URL. Header-supplied secrets are compared in constant
    #    time. Absent a session token, a valid header token is accepted for
    #    direct/back-compat callers.
    if not CALL_SERVER_TOKEN:
        await websocket.close(code=4003, reason="CALL_SERVER_TOKEN not configured")
        return
    state = websocket.app.state.call_state
    session_token = websocket.query_params.get("session")
    header_token = websocket.headers.get("x-call-token")
    authorized = state.consume_stream_token(session_token or "") or _tokens_match(
        header_token, CALL_SERVER_TOKEN
    )
    if not authorized:
        await websocket.close(code=4003, reason="Unauthorized")
        return

    # 2. Rate Limiting Request Rate — guarded so concurrent handlers can't
    #    over-commit the window via a check-then-mutate race across ``await``.
    client_ip = websocket.client.host if websocket.client else "unknown"
    now = time.time()
    async with _ips_lock:
        window = [t for t in client_ips[client_ip] if now - t < RATE_LIMIT_WINDOW]
        if len(window) >= MAX_REQUESTS_PER_WINDOW:
            client_ips[client_ip] = window
            await websocket.close(code=4029, reason="Rate limit exceeded")
            return
        window.append(now)
        client_ips[client_ip] = window

    # 3. Connection Limiting — atomically check-and-increment under the lock so
    #    MAX_CONCURRENT_CONNECTIONS is never over-committed.
    async with _conn_lock:
        if active_connections >= MAX_CONCURRENT_CONNECTIONS:
            await websocket.close(code=1013, reason="Server busy")
            return
        active_connections += 1
    try:
        print("Client connected")
        await websocket.accept()

        realtime_url, realtime_headers = _resolve_realtime_endpoint()
        async with websockets.connect(
            realtime_url,
            extra_headers=realtime_headers,
            # Bounded connect / heartbeat / close so a dead upstream cannot
            # hold a live Twilio media leg (and phone number) indefinitely.
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_size=2 ** 20,  # 1 MiB frame cap
        ) as openai_ws:
            await send_session_update(state, openai_ws)
            stream_sid = None

            async def receive_from_twilio():
                """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
                nonlocal stream_sid
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        if data['event'] == 'media' and openai_ws.open:
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Incoming stream has started {stream_sid}")
                except WebSocketDisconnect:
                    print("Client disconnected.")
                    if openai_ws.open:
                        await openai_ws.close()

            async def send_to_twilio():
                """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
                nonlocal stream_sid
                async for openai_message in openai_ws:
                    # Isolate per-event failures: a malformed message or an
                    # error handling a single event must not escape into
                    # asyncio.gather() and cancel the sibling Twilio task,
                    # which would drop the live call. Log and keep streaming.
                    try:
                        response = json.loads(openai_message)
                        if response['type'] in LOG_EVENT_TYPES:
                            print(f"Received event: {response['type']}", response)
                        if response['type'] == 'session.updated':
                            print("Session updated successfully:", response)

                        if response['type'] == 'response.done':
                            await handle_response_done(state, response, openai_ws)

                        if response['type'] == 'response.audio.delta' and response.get('delta'):
                            # Audio from OpenAI
                            audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            await websocket.send_json(audio_delta)
                    except Exception:
                        logger.exception("Error processing OpenAI event; continuing stream")

            await asyncio.gather(receive_from_twilio(), send_to_twilio())
    finally:
        async with _conn_lock:
            active_connections -= 1

async def handle_response_done(state, response, openai_ws):
    """Handle the response.done event and process any function calls."""
    print("Handling response.done:", response)
    output_items = response.get('response', {}).get('output', [])
    for item in output_items:
        if item.get('type') == 'function_call':
            await process_function_call(state, item, openai_ws)

async def process_function_call(state, item, openai_ws):
    """Process a function call item and send the result back to OpenAI."""
    function_name = item.get('name')
    arguments = json.loads(item.get('arguments', '{}'))
    call_id = item.get('call_id')

    print(f"Processing function call: {function_name}")
    print(f"Arguments: {arguments}")

    result = await call_tool(state, function_name, arguments)

    # Send the function call result back to OpenAI
    await openai_ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(result)
        }
    }))

    # Create a new response after sending the function call result
    await openai_ws.send(json.dumps({
        "type": "response.create"
    }))

async def call_tool(state, function_name, arguments):
    """Call the appropriate tool function and return the result."""
    tool = next((t for t in state.tools if t[0]['name'] == function_name), None)
    if not tool:
        return {"error": f"Function {function_name} not found"}
    
    try:
        # Assuming the tool function is the second element in the tuple
        result = await tool[1](**arguments)
        return result
    except Exception as e:
        return {"error": str(e)}

async def send_session_update(state, openai_ws):
    """Send session update to OpenAI WebSocket."""
    print(f"Formatted tools: {state.tools}")
    
    use_tools = [
        {**tool[0], "type": "function"}
        for tool in state.tools
        if isinstance(tool, tuple) and len(tool) > 0 and isinstance(tool[0], dict)
    ]
    
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 200
            },
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "tools": use_tools,
            "tool_choice": "auto",
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

def setup_public_url(port):
    from pyngrok import ngrok, conf

    if NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
    public_url = ngrok.connect(addr=str(port)).public_url
    print(f"Praison AI Voice URL: {public_url}")
    return public_url

def run_server(port: int, host: str = "127.0.0.1", use_public: bool = False):
    """Run the FastAPI server using uvicorn."""
    import uvicorn

    if not OPENAI_API_KEY:
        raise ValueError('Missing the OpenAI API key. Please set it in the .env file or configure it through the GUI.')
    
    if use_public:
        setup_public_url(port)
        host = "0.0.0.0"  # ngrok needs all-interfaces
    else:
        print(f"Starting Praison AI Call Server on http://{host}:{port}")
        
    # Log warning if binding to all interfaces without public flag
    if host == "0.0.0.0" and not use_public:
        print("WARNING: Server is binding to all network interfaces (0.0.0.0). "
              "This exposes the service to your local network.")

    os.environ["PRAISONAI_CALL_BIND_HOST"] = host

    # Build the app here (server entry point) — this is the only place local
    # tools.py is loaded, and only when PRAISONAI_ALLOW_LOCAL_TOOLS is set.
    app = build_call_app(load_local_tools=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")

def main(args=None):
    """Run the Praison AI Call Server."""
    # The ``praisonai call`` entry point runs a real server, so honour the
    # user's ``.env`` here (explicit run-time load, not an import-time side
    # effect). Module globals were captured at import — before this load — so
    # refresh the ones consumed at request time, otherwise a ``.env``-only
    # ``OPENAI_API_KEY``/``CALL_SERVER_TOKEN``/rate-limit would be ignored.
    from dotenv import load_dotenv
    load_dotenv()
    _refresh_env_globals()
    default_port = int(os.getenv('PORT', PORT))
    use_public_env = os.getenv('PUBLIC', 'false').lower() == 'true'

    parser = argparse.ArgumentParser(description="Run the Praison AI Call Server.")
    parser.add_argument('--public', action='store_true', help="Use ngrok to expose the server publicly")
    parser.add_argument('--port', type=int, default=default_port, help="Port to run the server on")
    parser.add_argument('--host', type=str, default="127.0.0.1", help="Host to bind the server to")

    if args is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(args)

    port = args.port
    host = args.host
    use_public = args.public or use_public_env

    run_server(port=port, host=host, use_public=use_public)

if __name__ == "__main__":
    main()
