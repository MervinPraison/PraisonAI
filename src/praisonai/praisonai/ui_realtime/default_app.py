"""PraisonAI Realtime UI — Voice realtime interface.

Loaded by ``praisonai ui realtime`` → ``aiui run app.py``.
Replaces ui/realtime.py (Chainlit) with aiui implementation.

Uses aiui's OpenAIRealtimeManager for WebRTC voice functionality.

Requires: pip install "praisonai[ui]"
"""

import os
from praisonai.integration.host_app import UIPreset, build_ui_app

app = build_ui_app(UIPreset(
    title="PraisonAI Realtime Voice",
    logo="🎤",
    pages=["chat", "sessions"],
    theme={"preset": "red", "dark_mode": True, "radius": "lg"},
    agent_kwargs={
        "name": "RealtimeAssistant",
        "instructions": "You are a voice-optimized assistant. Keep responses conversational and concise for voice interaction.",
        "llm": os.getenv("MODEL_NAME", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")),
    },
    starters=[
        {"label": "Voice Test", "message": "Test my microphone", "icon": "🎙️"},
        {"label": "Quick Chat", "message": "Let's have a conversation", "icon": "💬"},
        {"label": "Settings", "message": "Configure voice settings", "icon": "⚙️"},
        {"label": "Help", "message": "How do I use voice commands?", "icon": "❓"},
    ],
    welcome="🎤 Welcome to PraisonAI Realtime Voice! Click the microphone button to start talking.",
))