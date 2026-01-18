# Text-to-Speech with OpenAI
# Requires: export OPENAI_API_KEY=your-key

from praisonaiagents import AudioAgent

agent = AudioAgent(llm="openai/tts-1")
agent.say("Hello world!", output="hello.mp3")
print("Saved to hello.mp3")
