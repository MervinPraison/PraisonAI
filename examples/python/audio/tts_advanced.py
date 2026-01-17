from praisonaiagents import AudioAgent

agent = AudioAgent(llm="openai/tts-1-hd")
agent.speech("Hello!", voice="nova", speed=1.2, output="hello.mp3")

# Voices: alloy, echo, fable, onyx, nova, shimmer
# Models: openai/tts-1, openai/tts-1-hd, openai/gpt-4o-mini-tts
