"""PraisonAI Bot UI — Bot interface with step visualization.

Loaded by ``praisonai ui bot`` → ``aiui run app.py``.
Replaces ui/bot.py (Chainlit) with aiui implementation.

Requires: pip install "praisonai[ui]"
"""

import os
import praisonaiui as aiui
from praisonai.ui._aiui_datastore import PraisonAISessionDataStore

# ── Set up datastore bridge ─────────────────────────────────
aiui.set_datastore(PraisonAISessionDataStore())

# ── Dashboard style ─────────────────────────────────────────
aiui.set_style("dashboard")
aiui.set_branding(title="PraisonAI Bot", logo="🤖")
aiui.set_theme(preset="green", dark_mode=True, radius="lg")
aiui.set_pages([
    "chat",
    "sessions",
])

@aiui.starters
async def get_starters():
    """Suggest bot interaction starters."""
    return [
        {"label": "Help", "message": "What can you help me with?", "icon": "❓"},
        {"label": "Status", "message": "What's your current status?", "icon": "📊"},
        {"label": "Commands", "message": "What commands do you understand?", "icon": "⌨️"},
        {"label": "About", "message": "Tell me about yourself", "icon": "ℹ️"},
    ]

@aiui.welcome
async def on_welcome():
    """Welcome message for bot interface."""
    await aiui.say("🤖 Hi! I'm your PraisonAI Bot. I can help with various tasks and show you step-by-step reasoning.")

# Session-scoped bot cache
_bots_cache = {}

@aiui.reply
async def on_message(message: str):
    """Handle bot interactions with step visualization."""
    session_id = getattr(aiui.current_session, 'id', 'default')
    
    # Show initial thinking step
    await aiui.think("🤔 Analyzing request...")
    
    try:
        from praisonaiagents import Agent
        
        # Create or get cached bot agent
        if session_id not in _bots_cache:
            _bots_cache[session_id] = Agent(
                name="PraisonBot",
                instructions="You are a helpful bot assistant. Break down your reasoning into clear steps.",
                llm=os.getenv("MODEL_NAME", "gpt-4o-mini"),
            )
        
        bot = _bots_cache[session_id]
        
        # Execute with step visualization
        await aiui.think("⚙️ Processing...")
        
        result = await bot.achat(str(message))
        
        # Stream the response with step markers
        response_text = str(result) if result else "No response from bot"
        
        # Add step visualization
        await aiui.say("**🔄 Step 1: Analysis Complete**")
        await aiui.think("📤 Generating response...")
        
        # Stream the main response
        words = response_text.split(" ")
        for i, word in enumerate(words):
            await aiui.stream_token(word + (" " if i < len(words) - 1 else ""))
        
        await aiui.say("\n\n**✅ Step 2: Response Generated**")
            
    except Exception as e:
        await aiui.say(f"❌ Bot Error: {e}")
        await aiui.say("Please check your configuration and try again.")

@aiui.cancel
async def on_cancel():
    await aiui.say("⏹️ Bot interaction cancelled.")