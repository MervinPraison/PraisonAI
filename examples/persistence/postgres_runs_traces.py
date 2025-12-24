"""
PostgreSQL with Runs and Traces

Demonstrates full persistence with run tracking and tracing.

Run:
    python postgres_runs_traces.py

Expected output:
    - Agent responds with tool usage
    - Runs and traces are persisted
    - Export shows full session data
"""

from praisonaiagents import Agent, db

def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"

# Create database with PostgreSQL + Redis
my_db = db.PraisonDB(
    database_url="postgresql://postgres:praison123@localhost:5432/praisonai",
    state_url="redis://localhost:6379"
)

# Create agent with tools
agent = Agent(
    name="WeatherBot",
    instructions="You help with weather. Use the get_weather tool when asked.",
    tools=[get_weather],
    db=my_db,
    session_id="weather-session-001"
)

# First chat - triggers run tracking
print("=== First Question ===")
response1 = agent.chat("What's the weather in Tokyo?")
print(f"Response: {response1}\n")

# Second chat - same session, new run
print("=== Second Question ===")
response2 = agent.chat("How about New York?")
print(f"Response: {response2}\n")

# Export session data
print("=== Session Data ===")
data = my_db.export_session("weather-session-001")
print(f"Session ID: {data.get('session_id')}")
print(f"Messages: {len(data.get('messages', []))}")
print(f"Agent: {data.get('agent_name')}")

# Show messages
print("\n=== Messages ===")
for msg in data.get('messages', []):
    role = msg.get('role', 'unknown')
    content = msg.get('content', '')[:60]
    print(f"  [{role}] {content}...")

my_db.close()
print("\n✅ Done")
