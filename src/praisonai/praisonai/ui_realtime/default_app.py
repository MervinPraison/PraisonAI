"""PraisonAI Realtime UI — Voice realtime interface.

Loaded by ``praisonai ui realtime`` → ``aiui run app.py``.
Replaces ui/realtime.py (Chainlit) with aiui implementation.

Uses aiui's OpenAIRealtimeManager for WebRTC voice functionality.

Requires: pip install "praisonai[ui]"
"""

import os
import praisonaiui as aiui
from praisonaiui.features.realtime import OpenAIRealtimeManager
from praisonai.ui._aiui_datastore import PraisonAISessionDataStore

# ── Set up datastore bridge and realtime manager ───────────
aiui.set_datastore(PraisonAISessionDataStore())
aiui.set_realtime_manager(OpenAIRealtimeManager())

# ── Dashboard style ─────────────────────────────────────────
aiui.set_style("dashboard")
aiui.set_branding(title="PraisonAI Realtime Voice", logo="🎤")
aiui.set_theme(preset="red", dark_mode=True, radius="lg")
aiui.set_pages([
    "chat",
    "sessions",
])

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

# Session-scoped realtime agent cache
_realtime_cache = {}

@aiui.reply
async def on_message(message: str):
    """Handle realtime interactions via voice or text."""
    session_id = getattr(aiui.current_session, 'id', 'default')
    
    await aiui.think("🎤 Processing realtime request...")
    
    try:
        from praisonaiagents import Agent
        
        # Create or get cached realtime agent
        if session_id not in _realtime_cache:
            _realtime_cache[session_id] = Agent(
                name="RealtimeAssistant",
                instructions="You are a voice-optimized assistant. Keep responses conversational and concise for voice interaction.",
                llm=os.getenv("MODEL_NAME", "gpt-4o-mini"),
            )
        
        agent = _realtime_cache[session_id]
        
        # Process the message with the agent
        result = await agent.achat(str(message))
        
        # Stream response naturally (aiui handles voice output via WebRTC)
        response_text = str(result) if result else "I'm sorry, I couldn't process that."
        
        # Stream tokens for smooth output
        words = response_text.split(" ")
        for i, word in enumerate(words):
            await aiui.stream_token(word + (" " if i < len(words) - 1 else ""))
            
    except Exception as e:
        await aiui.say(f"❌ Realtime Error: {e}")

@aiui.cancel
async def on_cancel():
    await aiui.say("🔇 Realtime interaction stopped.")