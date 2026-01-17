from praisonaiagents import AudioAgent

agent = AudioAgent(llm="groq/whisper-large-v3")  # 10x faster
text = agent.transcribe("audio.mp3", language="en")
print(text)

# Models: openai/whisper-1, groq/whisper-large-v3, deepgram/nova-2
