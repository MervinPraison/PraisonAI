"""PraisonAI Realtime UI — Voice realtime interface.

Loaded by ``praisonai ui realtime`` → ``aiui run app.py``.
Replaces ui/realtime.py (Chainlit) with aiui implementation.

Uses aiui's OpenAIRealtimeManager for WebRTC voice functionality.

Requires: pip install "praisonai[ui]"
"""

import os

import praisonaiui as aiui
from praisonai.integration.host_app import configure_host, create_host_app, is_legacy_host
from praisonaiui.features.realtime import OpenAIRealtimeManager

configure_host(
    title="PraisonAI Realtime Voice",
    logo="🎤",
    pages=["chat", "sessions"],
    theme={"preset": "red", "dark_mode": True, "radius": "lg"},
    agent_kwargs={
        "name": "RealtimeAssistant",
        "instructions": (
            "You are a voice-optimized assistant. "
            "Keep responses conversational and concise for voice interaction."
        ),
        "llm": os.getenv("MODEL_NAME", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
    },
)

aiui.set_realtime_manager(OpenAIRealtimeManager())


@aiui.starters
async def get_starters():
    """Realtime conversation starters."""
    return [
        {"label": "Voice Test", "message": "Test voice interaction", "icon": "🎤"},
        {"label": "Realtime Help", "message": "How does realtime voice work?", "icon": "❓"},
        {"label": "Features", "message": "What realtime features are available?", "icon": "⚡"},
    ]


@aiui.welcome
async def on_welcome():
    """Welcome with realtime status."""
    await aiui.say("""🎤 **PraisonAI Realtime Voice Interface**

Welcome to PraisonAI's voice-powered realtime chat! Use the microphone button to start voice conversations with AI agents.

✨ Features:
- Real-time voice input/output via WebRTC
- Session persistence across restarts 
- Dashboard with chat history and usage logs
""")


if is_legacy_host():
    _realtime_cache = {}

    @aiui.reply
    async def on_message(message: str):
        """Handle realtime interactions via voice or text."""
        session_id = getattr(aiui.current_session, "id", "default")
        await aiui.think("🎤 Processing realtime request...")

        try:
            from praisonaiagents import Agent

            if session_id not in _realtime_cache:
                _realtime_cache[session_id] = Agent(
                    name="RealtimeAssistant",
                    instructions=(
                        "You are a voice-optimized assistant. "
                        "Keep responses conversational and concise for voice interaction."
                    ),
                    llm=os.getenv("MODEL_NAME", "gpt-4o-mini"),
                )

            agent = _realtime_cache[session_id]
            result = await agent.achat(str(message))
            response_text = str(result) if result else "I'm sorry, I couldn't process that."

            words = response_text.split(" ")
            for i, word in enumerate(words):
                await aiui.stream_token(word + (" " if i < len(words) - 1 else ""))

        except Exception as e:
            await aiui.say(f"❌ Realtime Error: {e}")

    @aiui.cancel
    async def on_cancel():
        await aiui.say("🔇 Realtime interaction stopped.")


app = create_host_app()
