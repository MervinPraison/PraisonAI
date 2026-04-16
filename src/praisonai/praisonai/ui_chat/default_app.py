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


_agent = None

@aiui.settings
async def on_settings(new_settings):
    global _agent
    _agent = None  # invalidate cache on change

def _get_agent(settings):
    global _agent
    if _agent is None:
        try:
            from praisonaiagents import Agent
            from praisonai.ui._external_agents import external_agent_tools
            
            # Get external agent tools based on settings
            tools = external_agent_tools(settings or {}, workspace=os.environ.get("PRAISONAI_WORKSPACE", "."))
            
            _agent = Agent(
                name="PraisonAI",
                instructions="You are a helpful assistant. Delegate coding/analysis tasks to external subagents when available.",
                llm=os.getenv("MODEL_NAME", "gpt-4o-mini"),
                tools=tools if tools else None,
            )
        except ImportError:
            # Fallback to OpenAI if PraisonAI agents not available
            _agent = None
    return _agent

@aiui.reply
async def on_message(message: str, settings: dict = None):
    """Stream a response using PraisonAI Agent or fallback to OpenAI."""
    await aiui.think("Thinking...")
    
    # Try PraisonAI Agent first
    agent = _get_agent(settings)
    if agent is not None:
        try:
            # Use agent.start() for synchronous call - agent handles async internally
            result = agent.start(str(message))
            # Stream the response token by token
            for chunk in str(result).split(" "):
                await aiui.stream_token(chunk + " ")
            return
        except Exception as e:
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
