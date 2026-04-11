import json
import pathlib
from praisonai import Agent, ManagedAgent, ManagedConfig

IDS_FILE = pathlib.Path("managed_ids.json")

if IDS_FILE.exists():
    saved = json.loads(IDS_FILE.read_text())
    print(f"Resuming session: {saved['session_id']}\n")

    managed = ManagedAgent()
    managed.resume_session(saved["session_id"])

    agent = Agent(name="coder", backend=managed)
    result = agent.start("What is my favourite number?", stream=True)

else:
    managed = ManagedAgent(
        config=ManagedConfig(
            name="Persistent Coder",
            model="claude-haiku-4-5",
            system="You are a helpful coding assistant.",
        ),
    )
    agent = Agent(name="coder", backend=managed)
    result = agent.start("Remember this: my favourite number is 42.", stream=True)

    ids = managed.save_ids()
    IDS_FILE.write_text(json.dumps(ids, indent=2))

    print(f"\nSaved IDs to {IDS_FILE}")
    print(f"  agent_id      : {managed.agent_id}")
    print(f"  environment_id: {managed.environment_id}")
    print(f"  session_id    : {managed.session_id}")
    print("\nRun this script again to resume the session.")
