"""PraisonAI Realtime UI — Voice realtime interface.

Loaded by ``praisonai ui realtime`` → ``aiui run app.py``.
Replaces ui/realtime.py (Chainlit) with aiui implementation.

NOTE: This is a placeholder implementation. Full WebRTC voice realtime
requires PraisonAIUI WebRTC feature to be implemented.

Requires: pip install "praisonai[ui]"
"""

import os
import praisonaiui as aiui
from praisonai.ui._aiui_datastore import PraisonAISessionDataStore

# ── Set up datastore bridge ─────────────────────────────────
aiui.set_datastore(PraisonAISessionDataStore())

# ── Dashboard style ─────────────────────────────────────────
aiui.set_style("dashboard")
aiui.set_branding(title="PraisonAI Realtime (Beta)", logo="🎤")
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
    await aiui.say("""🎤 **PraisonAI Realtime Voice Interface (Beta)**

⚠️ **Note**: Full WebRTC voice realtime is pending PraisonAIUI feature implementation.

For now, this provides a text-based interface that simulates realtime interactions.

See: https://github.com/MervinPraison/PraisonAIUI/issues for WebRTC voice realtime status.
""")

# Session-scoped realtime agent cache
_realtime_cache = {}

@aiui.reply
async def on_message(message: str):
    """Handle realtime interactions (text-based for now)."""
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
        
        # For now, process as text (voice coming in future PraisonAIUI release)
        result = await agent.achat(str(message))
        
        # Stream response (simulating voice output)
        response_text = str(result) if result else "I'm sorry, I couldn't process that."
        
        await aiui.say("🔊 **Voice Output Simulation:**\n")
        
        # Stream more slowly to simulate speech
        words = response_text.split(" ")
        for i, word in enumerate(words):
            await aiui.stream_token(word + (" " if i < len(words) - 1 else ""))
        
        await aiui.say("\n\n*Note: Actual voice I/O will be available when PraisonAIUI WebRTC feature lands.*")
            
    except Exception as e:
        await aiui.say(f"❌ Realtime Error: {e}")

@aiui.cancel
async def on_cancel():
    await aiui.say("🔇 Realtime interaction stopped.")