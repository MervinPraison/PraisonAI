"""
Realtime Capability Example

Demonstrates realtime session creation for audio/video streaming.
"""

from praisonai.capabilities import realtime_connect

# Create a realtime session
print("=== Realtime Session ===")
session = realtime_connect(
    model="gpt-4o-realtime-preview",
    modalities=["text", "audio"],
    voice="alloy"
)
print(f"Session ID: {session.id}")
print(f"Status: {session.status}")
print(f"URL: {session.url}")
print(f"Modalities: {session.metadata.get('modalities')}")
print(f"Voice: {session.metadata.get('voice')}")

print("\nNote: To use this session, connect via WebSocket to the URL above.")
print("See OpenAI Realtime API documentation for WebSocket protocol details.")
