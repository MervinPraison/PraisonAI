from praisonaiagents import Session

# Create a session with ID
session = Session(
    session_id="chat_123",
    user_id="user_456"
)

agent = session.Agent(
    name="Assistant",
    instructions="You are a helpful assistant with memory.",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    verbose=False,
    memory=True
)

response1 = agent.chat("My name is John")

print("response1", response1)

response2 = agent.chat("What's my name?")

print("response2", response2)

session.save_state({"conversation_topic": "Names"})

print("session", session)

anotherSession = Session(session_id="chat_123")
anotherSession.restore_state()

anotherAgent = anotherSession.Agent(
    name="Assistant",
    instructions="You are a helpful assistant with memory.",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    verbose=False,
    memory=True
)

response3 = anotherAgent.chat("What's my name?")
print("response3", response3)