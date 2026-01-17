from praisonaiagents import AudioAgent

agent = AudioAgent(llm="gemini/gemini-2.5-flash-preview-tts")
agent.say("Hello world!", output="hello.mp3", voice="leda")
