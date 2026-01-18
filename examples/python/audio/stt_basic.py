# Speech-to-Text with Groq (fastest)
# Requires: export GROQ_API_KEY=your-key

from praisonaiagents import AudioAgent

agent = AudioAgent(llm="groq/whisper-large-v3")
text = agent.listen("audio.mp3")  # Replace with your audio file
print(text)
