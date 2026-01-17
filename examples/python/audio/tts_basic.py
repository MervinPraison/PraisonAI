from praisonaiagents import AudioAgent

agent = AudioAgent(llm="openai/tts-1")
agent.say("Hello world!", output="hello.mp3")
