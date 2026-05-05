import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
import uvicorn
from pyngrok import ngrok, conf
from rich import print
import argparse
import logging
import importlib.util
import time
from collections import defaultdict

def _load_env_once():
    """Load environment variables from .env file once."""
    load_dotenv()

# Load env vars on module import for this specific API file
_load_env_once()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # requires OpenAI Realtime API Access
PORT = int(os.getenv('PORT', 8090))
NGROK_AUTH_TOKEN = os.getenv('NGROK_AUTH_TOKEN')
PUBLIC = os.getenv('PUBLIC', 'false').lower() == 'true'
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

app = FastAPI()

# Set up logging
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger.handlers.clear()

# Include agent invoke router for n8n integration
try:
    from .agent_invoke import router as agent_invoke_router
    app.include_router(agent_invoke_router)
    logger.debug("Agent invoke router added for n8n integration")
except ImportError as e:
    logger.warning(f"Could not load agent invoke router: {e}")

# Try to import tools from the root directory
tools = []
tools_path = os.path.join(os.getcwd(), 'tools.py')
logger.debug(f"Tools path: {tools_path}")

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

try:
    # Security: Require explicit opt-in for local tools loading
    if os.environ.get("PRAISONAI_ALLOW_LOCAL_TOOLS", "").lower() != "true":
        logger.debug("Local tools loading disabled. Set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable.")
        custom_tools_module = None
    elif os.path.exists(tools_path):
        # tools.py exists in the root directory, import from file
        custom_tools_module = import_tools_from_file(tools_path)
        logger.debug("Successfully imported custom tools from root tools.py")
    else:
        logger.debug("No custom tools.py file found in the root directory")
        custom_tools_module = None

    if custom_tools_module:
        # Update the tools list with custom tools
        if hasattr(custom_tools_module, 'tools') and isinstance(custom_tools_module.tools, list):
            tools.extend(custom_tools_module.tools)
        else:
            for name, obj in custom_tools_module.__dict__.items():
                if callable(obj) and not name.startswith("__"):
                    tool_definition = getattr(obj, 'definition', None)
                    if tool_definition:
                        tools.append(tool_definition)

except Exception as e:
    logger.warning(f"Error importing custom tools: {str(e)}. Continuing without custom tools.")

@app.get("/status", response_class=HTMLResponse)
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

from fastapi import HTTPException, status

@app.api_route("/", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    if CALL_SERVER_TOKEN:
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
                        token = decoded.split(":", 1)[1]  # Use Password as token
                    else:
                        token = decoded
                except Exception:
                    pass
        if token != CALL_SERVER_TOKEN:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    response = VoiceResponse()
    response.say("")
    response.pause(length=1)
    # response.say("")
    host = request.url.hostname
    connect = Connect()
    
    stream_url = f'wss://{host}/media-stream'
    if CALL_SERVER_TOKEN:
        stream_url += f'?token={CALL_SERVER_TOKEN}'
    
    connect.stream(url=stream_url)
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    global active_connections
    
    # 1. Authentication
    if CALL_SERVER_TOKEN:
        token = websocket.query_params.get("token")
        if token != CALL_SERVER_TOKEN:
            await websocket.close(code=4003, reason="Unauthorized")
            return
            
    # 2. Rate Limiting Request Rate
    client_ip = websocket.client.host if websocket.client else "unknown"
    now = time.time()
    client_ips[client_ip] = [t for t in client_ips[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(client_ips[client_ip]) >= MAX_REQUESTS_PER_WINDOW:
        await websocket.close(code=4029, reason="Rate limit exceeded")
        return
    client_ips[client_ip].append(now)
    
    # 3. Connection Limiting
    if active_connections >= MAX_CONCURRENT_CONNECTIONS:
        await websocket.close(code=1013, reason="Server busy")
        return
        
    active_connections += 1
    try:
        print("Client connected")
        await websocket.accept()

        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            await send_session_update(openai_ws)
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
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)
                    if response['type'] == 'session.updated':
                        print("Session updated successfully:", response)
                    
                    if response['type'] == 'response.done':
                        await handle_response_done(response, openai_ws)
                    
                    if response['type'] == 'response.audio.delta' and response.get('delta'):
                        # Audio from OpenAI
                        try:
                            audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            await websocket.send_json(audio_delta)
                        except Exception as e:
                            print(f"Error processing audio data: {e}")
            except Exception as e:
                print(f"Error in Sending to Phone: {e}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())
    finally:
        active_connections -= 1

async def handle_response_done(response, openai_ws):
    """Handle the response.done event and process any function calls."""
    print("Handling response.done:", response)
    output_items = response.get('response', {}).get('output', [])
    for item in output_items:
        if item.get('type') == 'function_call':
            await process_function_call(item, openai_ws)

async def process_function_call(item, openai_ws):
    """Process a function call item and send the result back to OpenAI."""
    function_name = item.get('name')
    arguments = json.loads(item.get('arguments', '{}'))
    call_id = item.get('call_id')

    print(f"Processing function call: {function_name}")
    print(f"Arguments: {arguments}")

    result = await call_tool(function_name, arguments)

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

async def call_tool(function_name, arguments):
    """Call the appropriate tool function and return the result."""
    tool = next((t for t in tools if t[0]['name'] == function_name), None)
    if not tool:
        return {"error": f"Function {function_name} not found"}
    
    try:
        # Assuming the tool function is the second element in the tuple
        result = await tool[1](**arguments)
        return result
    except Exception as e:
        return {"error": str(e)}

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    global tools
    print(f"Formatted tools: {tools}")
    
    use_tools = [
        {**tool[0], "type": "function"}
        for tool in tools
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
    if NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
    public_url = ngrok.connect(addr=str(port)).public_url
    print(f"Praison AI Voice URL: {public_url}")
    return public_url

def run_server(port: int, use_public: bool = False):
    """Run the FastAPI server using uvicorn."""
    if not OPENAI_API_KEY:
        raise ValueError('Missing the OpenAI API key. Please set it in the .env file or configure it through the GUI.')
    
    if use_public:
        setup_public_url(port)
    else:
        print(f"Starting Praison AI Call Server on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

def main(args=None):
    """Run the Praison AI Call Server."""
    parser = argparse.ArgumentParser(description="Run the Praison AI Call Server.")
    parser.add_argument('--public', action='store_true', help="Use ngrok to expose the server publicly")
    parser.add_argument('--port', type=int, default=PORT, help="Port to run the server on")

    if args is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(args)

    port = args.port
    use_public = args.public or PUBLIC

    run_server(port=port, use_public=use_public)

if __name__ == "__main__":
    main()
