"""Multi-Agent Shared Session Demo"""
from praisonaiagents import Agent
from praisonai.persistence import create_conversation_store

store = create_conversation_store("sqlite", path="/tmp/multi_agent.db")

agent1 = Agent(name="Researcher", llm="gpt-4o-mini", db=store, session_id="shared-session")
agent2 = Agent(name="Writer", llm="gpt-4o-mini", db=store, session_id="shared-session")

r1 = agent1.chat("Research topic: AI in healthcare. Key finding: reduces diagnosis time by 50%")
print(f"Researcher: {r1[:50]}...")

r2 = agent2.chat("Based on the research, what was the key finding?")
print(f"Writer: {r2[:50]}...")
assert "50" in r2 or "diagnosis" in r2.lower(), "Writer should see Researcher's context"
print("PASSED: Multi-agent shared session works")
