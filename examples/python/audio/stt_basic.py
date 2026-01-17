from praisonaiagents import AudioAgent

agent = AudioAgent(llm="openai/whisper-1")
text = agent.listen("audio.mp3")
print(text)
