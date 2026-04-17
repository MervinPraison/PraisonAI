"""PraisonAI Clean Chat UI — minimal chat interface.

Loaded by ``praisonai ui`` → ``aiui run app.py``.
Clean chat without sidebar navigation.

Requires: pip install "praisonai[ui]"
Set OPENAI_API_KEY before running.

Run:
    praisonai ui
"""

import os

import praisonaiui as aiui
from praisonai.ui._aiui_datastore import PraisonAISessionDataStore

# ── Set up datastore bridge ─────────────────────────────────
aiui.set_datastore(PraisonAISessionDataStore())

# ── Dashboard style, but no sidebar navigation ─────────────
aiui.set_style("dashboard")
aiui.set_dashboard(sidebar=False, page_header=False)
aiui.set_branding(title="PraisonAI Chat", logo="🤖")
aiui.set_theme(preset="blue", dark_mode=True, radius="lg")
aiui.set_pages(["chat"])

# Add external agent settings
try:
    from praisonai.ui._external_agents import aiui_settings_entries
    external_settings = aiui_settings_entries()
    if external_settings:
        aiui.set_settings(external_settings)
except ImportError:
    # External agents not available
    pass


@aiui.starters
async def get_starters():
    """Suggest conversation starters."""
    return [
        {"label": "Research", "message": "Research the latest AI trends", "icon": "🔬"},
        {"label": "Write", "message": "Write a blog post about AI agents", "icon": "✍️"},
        {"label": "Code", "message": "Write a Python function to sort a list", "icon": "💻"},
        {"label": "Brainstorm", "message": "Give me 5 startup ideas using AI agents", "icon": "💡"},
    ]


@aiui.welcome
async def on_welcome():
    """Greet the user."""
    await aiui.say("👋 Hi! I'm your PraisonAI assistant. Ask me anything!")


# Session-scoped agent cache to avoid cross-user state leaks
_agents_cache = {}

@aiui.settings
async def on_settings(new_settings):
    # Clear cache for current session when settings change
    session_id = getattr(aiui.current_session, 'id', 'default')
    if session_id in _agents_cache:
        del _agents_cache[session_id]

def _get_agent(settings: dict | None = None):
    session_id = getattr(aiui.current_session, 'id', 'default')
    settings_key = str(sorted((settings or {}).items()))
    cache_key = f"{session_id}:{settings_key}"
    
    if cache_key not in _agents_cache:
        try:
            from praisonaiagents import Agent
            from praisonai.ui._external_agents import external_agent_tools
            
            # Get external agent tools based on settings
            tools = external_agent_tools(settings or {}, workspace=os.environ.get("PRAISONAI_WORKSPACE", "."))
            
            agent = Agent(
                name="PraisonAI",
                instructions="You are a helpful assistant. Delegate coding/analysis tasks to external subagents when available.",
                llm=os.getenv("MODEL_NAME", "gpt-4o-mini"),
                tools=tools if tools else None,
            )
            _agents_cache[cache_key] = agent
        except ImportError:
            # Fallback to OpenAI if PraisonAI agents not available
            _agents_cache[cache_key] = None
    return _agents_cache[cache_key]

@aiui.reply
async def on_message(message: str, settings: dict | None = None):
    """Stream a response using PraisonAI Agent or fallback to OpenAI."""
    await aiui.think("Thinking...")
    
    # Try PraisonAI Agent first
    agent = _get_agent(settings)
    if agent is not None:
        try:
            # Use async call to avoid blocking the event loop
            result = await agent.achat(str(message))
            response_text = str(result) if result else ""
            words = response_text.split(" ")
            for i, word in enumerate(words):
                await aiui.stream_token(word + (" " if i < len(words) - 1 else ""))
            return
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Agent execution failed")
            await aiui.say(f"⚠️ Agent error: {e}. Falling back to OpenAI...")
    
    # Fallback to direct OpenAI
    try:
        from openai import AsyncOpenAI
    except ImportError:
        await aiui.say("❌ Please install openai: `pip install openai`")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        await aiui.say("❌ Please set OPENAI_API_KEY environment variable.")
        return

    client = AsyncOpenAI(api_key=api_key)
    stream = await client.chat.completions.create(
        model=os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "You are a helpful, concise assistant. Use markdown for formatting."},
            {"role": "user", "content": str(message)},
        ],
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            await aiui.stream_token(delta.content)


@aiui.cancel
async def on_cancel():
    await aiui.say("⏹️ Stopped.")
