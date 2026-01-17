from praisonaiagents import AudioAgent

agent = AudioAgent(llm="deepgram/nova-2")
text = agent.listen("audio.mp3")
print(text)
