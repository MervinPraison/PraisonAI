from praisonaiagents import AudioAgent

agent = AudioAgent(llm="elevenlabs/eleven_multilingual_v2")
agent.say("Hello world!", output="hello.mp3")
