from praisonaiagents import AudioAgent

# Text to Speech
tts = AudioAgent(llm="openai/tts-1")
tts.say("Hello!", output="hello.mp3")

# Speech to Text
stt = AudioAgent(llm="openai/whisper-1")
text = stt.listen("hello.mp3")
print(text)
