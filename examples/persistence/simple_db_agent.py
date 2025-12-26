"""
Simple Database Persistence Example for PraisonAI Agents.

This example shows how to enable automatic conversation persistence
with just 2 lines of code.

Requirements:
    pip install "praisonai[tools]"
    
Docker Setup:
    docker run -d --name praison-postgres -p 5432:5432 \
        -e POSTGRES_PASSWORD=praison123 \
        -e POSTGRES_DB=praisonai \
        postgres:16

Environment:
    export OPENAI_API_KEY=your-key

Run:
    python simple_agent_postgres.py

Expected Output:
    === First Run ===
    Agent: Nice to meet you, Alice! Python is a great choice...
    Session ID: demo-session-001
    Messages persisted: 2
"""

from praisonaiagents import Agent, db

# Create database adapter (simplified import)
db_instance = db(
    database_url="postgresql://postgres:praison123@localhost:5432/praisonai"
)

# Create agent with persistence enabled
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant. Keep responses brief.",
    db=db_instance,
    session_id="demo-session-001",  # Same session_id = resume conversation
    verbose=False
)

# Chat with persistence
print("=== First Run ===")
response = agent.chat("My name is Alice and I love Python programming.")
print(f"Agent: {response}\n")

# Show session info
print(f"Session ID: {agent.session_id}")
print(f"Messages in history: {len(agent.chat_history)}")

# Close DB connection
db_instance.close()

print("\n=== Session persisted! ===")
print("Run again with same session_id to resume.")
