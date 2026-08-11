# praisonai: skip=true
# Requires local audio.mp3 fixture
from praisonaiagents import AudioAgent

agent = AudioAgent(llm="groq/whisper-large-v3")
text = agent.listen("audio.mp3")
print(text)

