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
from praisonai.integration.host_app import configure_host, create_host_app, is_legacy_host

configure_host(
    title="PraisonAI Chat",
    logo="🤖",
    pages=["chat"],
    sidebar=False,
    page_header=False,
    theme={"preset": "blue", "dark_mode": True, "radius": "lg"},
    agent_kwargs={
        "name": "PraisonAI",
        "instructions": (
            "You are a helpful assistant. Delegate coding/analysis tasks "
            "to external subagents when available."
        ),
        "llm": os.getenv("MODEL_NAME", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
    },
)


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


if is_legacy_host():
    _agents_cache = {}

    @aiui.settings
    async def on_settings(new_settings):
        session_id = getattr(aiui.current_session, "id", "default")
        _agents_cache.pop(session_id, None)

    def _get_agent(settings: dict | None = None):
        session_id = getattr(aiui.current_session, "id", "default")
        settings_key = str(sorted((settings or {}).items()))
        cache_key = f"{session_id}:{settings_key}"

        if cache_key not in _agents_cache:
            try:
                from praisonaiagents import Agent
                from praisonai.ui._external_agents import external_agent_tools

                tools = external_agent_tools(
                    settings or {},
                    workspace=os.environ.get("PRAISONAI_WORKSPACE", "."),
                )
                _agents_cache[cache_key] = Agent(
                    name="PraisonAI",
                    instructions=(
                        "You are a helpful assistant. Delegate coding/analysis tasks "
                        "to external subagents when available."
                    ),
                    llm=os.getenv("MODEL_NAME", "gpt-4o-mini"),
                    tools=tools if tools else None,
                )
            except ImportError:
                _agents_cache[cache_key] = None
        return _agents_cache[cache_key]

    @aiui.reply
    async def on_message(message: str, settings: dict | None = None):
        """Stream a response using PraisonAI Agent or fallback to OpenAI."""
        await aiui.think("Thinking...")

        agent = _get_agent(settings)
        if agent is not None:
            try:
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
                {
                    "role": "system",
                    "content": "You are a helpful, concise assistant. Use markdown for formatting.",
                },
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


app = create_host_app()
