"""PraisonAI Bot UI - Chainlit chat interface with real-time streaming.

Provides a browser-based chat UI backed by PraisonAI Agent with:
- Real-time token streaming via StreamEventEmitter (not fake word-splitting)
- Tool call visualization as Chainlit Steps (Chain of Thought)
- MESSAGE_RECEIVED/SENDING/SENT hook firing
- Full bot capabilities (memory, web search, tools, etc.)
- Gateway connectivity (if configured)

Usage:
    praisonai ui bot
    praisonai ui bot --model gpt-4o --memory --web
    praisonai ui bot --agent agents.yaml --tools DuckDuckGoTool
"""

import asyncio
import logging
import os
import queue

import chainlit as cl
from chainlit.input_widget import TextInput, Switch

logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper() or "INFO"
logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")

# Auth secret (required by Chainlit)
if not os.getenv("CHAINLIT_AUTH_SECRET"):
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------
_cache = {}


def _get_agent_class():
    if "Agent" not in _cache:
        from praisonaiagents import Agent
        _cache["Agent"] = Agent
    return _cache["Agent"]


def _get_stream_event_type():
    if "StreamEventType" not in _cache:
        from praisonaiagents.streaming.events import StreamEventType
        _cache["StreamEventType"] = StreamEventType
    return _cache["StreamEventType"]


def _get_bot_handler():
    """Reuse BotHandler._build_tools / _load_agent for DRY tool resolution."""
    if "BotHandler" not in _cache:
        from praisonai.cli.features.bots_cli import BotHandler
        _cache["BotHandler"] = BotHandler
    return _cache["BotHandler"]


def _get_bot_capabilities():
    if "BotCapabilities" not in _cache:
        from praisonai.cli.features.bots_cli import BotCapabilities
        _cache["BotCapabilities"] = BotCapabilities
    return _cache["BotCapabilities"]


# ---------------------------------------------------------------------------
# Environment-driven config (set by CLI before launching chainlit)
# ---------------------------------------------------------------------------
def _get_config():
    """Read bot config from environment (set by CLI command)."""
    return {
        "model": os.getenv("PRAISONAI_BOT_MODEL", "gpt-4o-mini"),
        "agent_file": os.getenv("PRAISONAI_BOT_AGENT_FILE"),
        "memory": os.getenv("PRAISONAI_BOT_MEMORY", "").lower() in ("1", "true"),
        "web_search": os.getenv("PRAISONAI_BOT_WEB_SEARCH", "").lower() in ("1", "true"),
        "web_provider": os.getenv("PRAISONAI_BOT_WEB_PROVIDER", "duckduckgo"),
        "tools": [t.strip() for t in os.getenv("PRAISONAI_BOT_TOOLS", "").split(",") if t.strip()],
        "auto_approve": os.getenv("PRAISONAI_BOT_AUTO_APPROVE", "").lower() in ("1", "true"),
    }


# ---------------------------------------------------------------------------
# Agent factory (reuses BotHandler patterns)
# ---------------------------------------------------------------------------
def _create_agent(model: str = None, memory: bool = False, web_search: bool = False,
                  web_provider: str = "duckduckgo", tools_list: list = None,
                  agent_file: str = None, auto_approve: bool = False):
    """Create a PraisonAI Agent with capabilities, reusing BotHandler patterns."""
    BotCapabilities = _get_bot_capabilities()
    BotHandler = _get_bot_handler()

    config = _get_config()
    model = model or config["model"]
    memory = memory or config["memory"]
    web_search = web_search or config["web_search"]
    web_provider = web_provider or config["web_provider"]
    tools_list = tools_list or config["tools"]
    agent_file = agent_file or config["agent_file"]
    auto_approve = auto_approve or config["auto_approve"]

    caps = BotCapabilities(
        model=model,
        memory=memory,
        web_search=web_search,
        web_search_provider=web_provider,
        tools=tools_list or [],
        auto_approve=auto_approve,
    )

    if auto_approve:
        os.environ["PRAISONAI_AUTO_APPROVE"] = "true"

    handler = BotHandler()
    agent = handler._load_agent(agent_file, caps)
    return agent


# ---------------------------------------------------------------------------
# Streaming bridge: StreamEventEmitter (sync, in thread) → asyncio.Queue → cl.stream_token (async)
# Pattern reused from gateway/server.py _make_stream_relay
# ---------------------------------------------------------------------------

# Sentinel to signal stream end
_STREAM_END = object()


def _make_chainlit_relay(event_queue: queue.Queue):
    """Create a sync StreamCallback that puts events into a thread-safe queue.

    This callback is registered on agent.stream_emitter and called from the
    LLM streaming thread (sync context). Events are consumed asynchronously
    by _consume_stream_events().
    """
    def _relay(event) -> None:
        try:
            event_queue.put_nowait(event)
        except Exception:
            pass  # Non-fatal: drop event if queue is full
    return _relay


async def _consume_stream_events(event_queue: queue.Queue, msg: cl.Message):
    """Async consumer: reads StreamEvents from queue and dispatches to Chainlit.

    Maps:
    - DELTA_TEXT → msg.stream_token(content)
    - DELTA_TOOL_CALL → open cl.Step(type="tool")
    - STREAM_END → finalize message
    """
    StreamEventType = _get_stream_event_type()
    open_steps = {}  # tool_call_index → cl.Step

    while True:
        # Poll queue without blocking the event loop
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.01)  # Yield to event loop
            continue

        if event is _STREAM_END:
            break

        event_type = getattr(event, "type", None)
        if event_type is None:
            continue

        try:
            if event_type == StreamEventType.DELTA_TEXT:
                content = getattr(event, "content", "") or ""
                if content:
                    await msg.stream_token(content)

            elif event_type == StreamEventType.DELTA_TOOL_CALL:
                tool_call = getattr(event, "tool_call", {}) or {}
                tc_index = tool_call.get("index", 0)
                tc_name = tool_call.get("name") or tool_call.get("function", {}).get("name")

                if tc_index not in open_steps and tc_name:
                    step = cl.Step(name=tc_name, type="tool")
                    step.input = ""
                    await step.send()
                    open_steps[tc_index] = step

                # Accumulate arguments into the step
                if tc_index in open_steps:
                    args_chunk = tool_call.get("arguments", "") or tool_call.get("function", {}).get("arguments", "")
                    if args_chunk:
                        open_steps[tc_index].input += args_chunk

            elif event_type == StreamEventType.TOOL_CALL_END:
                # Close all open steps
                for idx, step in list(open_steps.items()):
                    step.output = "Completed"
                    await step.update()
                open_steps.clear()

            elif event_type == StreamEventType.STREAM_END:
                break

            elif event_type == StreamEventType.ERROR:
                error_msg = getattr(event, "error", "Unknown error")
                await cl.Message(content=f"**Error:** {error_msg}", author="System").send()
                break

        except Exception as e:
            logger.debug(f"Stream event handling error (non-fatal): {e}")

    # Close any remaining open steps
    for step in open_steps.values():
        try:
            step.output = "Completed"
            await step.update()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Chainlit callbacks
# ---------------------------------------------------------------------------

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    expected_user = os.getenv("CHAINLIT_USERNAME", "admin")
    expected_pass = os.getenv("CHAINLIT_PASSWORD", "admin")
    if (username, password) == (expected_user, expected_pass):
        return cl.User(identifier=username, metadata={"role": "admin", "provider": "credentials"})
    return None


@cl.on_chat_start
async def on_chat_start():
    config = _get_config()

    # Create agent and store in session
    agent = _create_agent()
    cl.user_session.set("agent", agent)
    cl.user_session.set("model_name", config["model"])

    # Settings panel
    settings = cl.ChatSettings([
        TextInput(
            id="model_name",
            label="Model",
            placeholder="e.g. gpt-4o-mini",
            initial=config["model"],
        ),
        Switch(id="memory", label="Memory", initial=config["memory"]),
        Switch(id="web_search", label="Web Search", initial=config["web_search"]),
    ])
    await settings.send()

    # Startup message
    capabilities = []
    if config["memory"]:
        capabilities.append("Memory")
    if config["web_search"]:
        capabilities.append(f"Web Search ({config['web_provider']})")
    if config["tools"]:
        capabilities.append(f"Tools: {', '.join(config['tools'])}")

    caps_str = ", ".join(capabilities) if capabilities else "None"
    await cl.Message(
        content=(
            f"**PraisonAI Bot Ready**\n\n"
            f"**Model:** {config['model']}\n"
            f"**Capabilities:** {caps_str}\n\n"
            f"Type a message to start chatting!"
        )
    ).send()


@cl.on_settings_update
async def on_settings_update(settings):
    model = settings.get("model_name", "gpt-4o-mini")
    memory = settings.get("memory", False)
    web_search = settings.get("web_search", False)

    old_model = cl.user_session.get("model_name")

    # Recreate agent if settings changed
    if model != old_model or memory != _get_config()["memory"]:
        agent = _create_agent(model=model, memory=memory, web_search=web_search)
        cl.user_session.set("agent", agent)
        cl.user_session.set("model_name", model)
        await cl.Message(content=f"Settings updated. Model: **{model}**").send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages with real-time streaming."""
    agent = cl.user_session.get("agent")
    if agent is None:
        agent = _create_agent()
        cl.user_session.set("agent", agent)

    # Fire MESSAGE_RECEIVED hook (if hooks configured)
    _fire_hook_safe(agent, "MESSAGE_RECEIVED", {
        "content": message.content,
        "author": message.author or "user",
    })

    # Create empty message for streaming
    msg = cl.Message(content="")
    await msg.send()

    # Set up streaming bridge
    event_queue = queue.Queue(maxsize=10000)
    relay_callback = _make_chainlit_relay(event_queue)

    # Register callback on the agent's stream emitter
    emitter = getattr(agent, "stream_emitter", None)
    if emitter is not None:
        emitter.add_callback(relay_callback)

    # Start async consumer task
    consumer_task = asyncio.create_task(
        _consume_stream_events(event_queue, msg)
    )

    try:
        # Fire MESSAGE_SENDING hook
        _fire_hook_safe(agent, "MESSAGE_SENDING", {"content": message.content})

        # Run agent.chat in a thread (sync) — streaming events flow via the relay
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: agent.chat(message.content, stream=True)
        )

        # Signal stream end
        event_queue.put_nowait(_STREAM_END)

        # Wait for consumer to finish processing
        await consumer_task

        # Update message with final content
        if response:
            response_text = response if isinstance(response, str) else str(response)
            # Only update if streaming didn't already populate the content
            if not msg.content or len(msg.content.strip()) < 10:
                msg.content = response_text
            await msg.update()
        else:
            if not msg.content:
                msg.content = "No response from agent."
            await msg.update()

        # Fire MESSAGE_SENT hook
        _fire_hook_safe(agent, "MESSAGE_SENT", {
            "content": msg.content,
            "author": agent.name,
        })

    except Exception as e:
        logger.error(f"Agent chat error: {e}")
        event_queue.put_nowait(_STREAM_END)
        await consumer_task
        msg.content = f"Error: {str(e)}"
        await msg.update()

    finally:
        # Always clean up the relay callback
        if emitter is not None:
            try:
                emitter.remove_callback(relay_callback)
            except (ValueError, AttributeError):
                pass


def _fire_hook_safe(agent, hook_name: str, data: dict):
    """Fire a message lifecycle hook safely (non-blocking, non-fatal)."""
    try:
        runner = getattr(agent, "_hook_runner", None)
        if runner is None:
            return

        from praisonaiagents.hooks import HookEvent
        event = getattr(HookEvent, hook_name, None)
        if event is None:
            return

        # Build the appropriate input dataclass
        if hook_name == "MESSAGE_RECEIVED":
            from praisonaiagents.hooks.events import MessageReceivedInput
            hook_input = MessageReceivedInput(
                session_id=getattr(agent, "_session_id", "chainlit"),
                cwd=os.getcwd(),
                event_name=event,
                timestamp=str(__import__("time").time()),
                platform="chainlit",
                content=data.get("content", ""),
                sender_id=data.get("author", "user"),
            )
        elif hook_name == "MESSAGE_SENDING":
            from praisonaiagents.hooks.events import MessageSendingInput
            hook_input = MessageSendingInput(
                session_id=getattr(agent, "_session_id", "chainlit"),
                cwd=os.getcwd(),
                event_name=event,
                timestamp=str(__import__("time").time()),
                platform="chainlit",
                content=data.get("content", ""),
            )
        elif hook_name == "MESSAGE_SENT":
            from praisonaiagents.hooks.events import MessageSentInput
            hook_input = MessageSentInput(
                session_id=getattr(agent, "_session_id", "chainlit"),
                cwd=os.getcwd(),
                event_name=event,
                timestamp=str(__import__("time").time()),
                platform="chainlit",
                content=data.get("content", ""),
                message_id="",
            )
        else:
            return

        runner.execute_sync(event, hook_input)
    except Exception as e:
        logger.debug(f"Hook {hook_name} error (non-fatal): {e}")
