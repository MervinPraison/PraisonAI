import json
from praisonai import Agent, ManagedAgent, ManagedConfig

# 1. Create an agent

managed = ManagedAgent()
agent = Agent(name="teacher", backend=managed)
result = agent.start("Say hello briefly", stream=True)

print(f"[1] Agent created: {managed.agent_id} (v{managed.agent_version})")

# 2. Update the agent

managed.update_agent(
    name="Teaching Agent v2",
    system="You are a senior Python developer. Write clean, production-quality code.",
)

print(f"[2] Agent updated: Teaching Agent v2 (v{managed.agent_version})")

# 3-4. Environment + Session are created automatically (already done in step 1)

print(f"[3] Environment created: {managed.environment_id}")
print(f"[4] Session created: {managed.session_id}")

# 5. Stream a response

print("\n[5] Streaming response...")

result = agent.start("Write a Python script that prints 'Hello from Managed Agents!' and run it", stream=True)

# 6. Multi-turn conversation (same session remembers context)

print("\n[6] Multi-turn: sending follow-up...")

result = agent.start("Now modify that script to accept a name argument and greet that person", stream=True)

# 7. Track usage

info = managed.retrieve_session()
print("\n[7] Usage report:")
if info.get("usage"):
    print(f"    Input tokens:  {info['usage']['input_tokens']}")
    print(f"    Output tokens: {info['usage']['output_tokens']}")
else:
    print(f"    Input tokens:  {managed.total_input_tokens}")
    print(f"    Output tokens: {managed.total_output_tokens}")

# 8. List sessions

sessions = managed.list_sessions()
print(f"\n[8] Total sessions: {len(sessions)}")
for s in sessions[:3]:
    print(f"    {s['id']} | {s['status']} | {s['title']}")

# 9. Selective tools (only bash + read + write)

bash_managed = ManagedAgent(
    config=ManagedConfig(
        name="Bash Only Agent",
        model="claude-haiku-4-5",
        system="You can only use bash, read, and write tools.",
        tools=[
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": False},
                "configs": [
                    {"name": "bash", "enabled": True},
                    {"name": "read", "enabled": True},
                    {"name": "write", "enabled": True},
                ],
            },
        ],
    ),
)

bash_agent = Agent(name="bash-only", backend=bash_managed)

print("\n[9] Bash-only agent streaming...")
result = bash_agent.start("Show the current date and Python version using bash", stream=True)

# 10. Disable specific tools (web disabled, everything else on)

no_web_managed = ManagedAgent(
    config=ManagedConfig(
        name="No Web Agent",
        model="claude-haiku-4-5",
        system="You are a coding assistant. You cannot access the web.",
        tools=[
            {
                "type": "agent_toolset_20260401",
                "configs": [
                    {"name": "web_fetch", "enabled": False},
                    {"name": "web_search", "enabled": False},
                ],
            },
        ],
    ),
)

no_web_agent = Agent(name="no-web", backend=no_web_managed)

print("\n[10] No-web agent streaming...")
result = no_web_agent.start("Write a Python one-liner that calculates 2**100 and print the result", stream=True)

# 11. Custom tools (you define the tool, PraisonAI calls your callback)


def handle_weather(tool_name, tool_input):
    print(f"\n  [Custom tool: {tool_name} | Input: {json.dumps(tool_input)}]")
    return "Tokyo: 22°C, sunny, humidity 55%"


custom_managed = ManagedAgent(
    config=ManagedConfig(
        name="Weather Agent",
        model="claude-haiku-4-5",
        system="You are a weather assistant. Use the get_weather tool to check weather.",
        tools=[
            {"type": "agent_toolset_20260401"},
            {
                "type": "custom",
                "name": "get_weather",
                "description": "Get current weather for a location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            },
        ],
    ),
    on_custom_tool=handle_weather,
)

custom_agent = Agent(name="weather", backend=custom_managed)

print("\n[11] Custom tool agent streaming...")
result = custom_agent.start("What is the weather in Tokyo?", stream=True)

# 12. Web search agent

search_managed = ManagedAgent(
    config=ManagedConfig(
        name="Search Agent",
        model="claude-haiku-4-5",
        system="You are a research assistant. Search the web and summarize.",
    ),
)

search_agent = Agent(name="searcher", backend=search_managed)

print("\n[12] Web search agent streaming...")
result = search_agent.start("Search the web for Python 3.13 new features and give me 3 bullet points", stream=True)

# 13. Environment with pre-installed packages

data_managed = ManagedAgent(
    config=ManagedConfig(
        name="Data Science Agent",
        model="claude-haiku-4-5",
        system="You are a data science assistant.",
        packages={"pip": ["pandas", "numpy"]},
    ),
)

data_agent = Agent(name="data-scientist", backend=data_managed)

print("\n[13] Data science environment streaming...")
result = data_agent.start("Use pandas to create a small DataFrame with 3 rows of sample data and print it", stream=True)

# 14. Interrupt a session

interrupt_managed = ManagedAgent(
    config=ManagedConfig(
        name="Interruptable Agent",
        model="claude-haiku-4-5",
        system="You are a helpful coding assistant.",
    ),
)

interrupt_agent = Agent(name="interruptable", backend=interrupt_managed)

print("\n[14] Interrupt demo...")
result = interrupt_agent.start("Write a Python script that prints numbers 1 to 10", stream=True)
interrupt_managed.interrupt()
print("  [Interrupt sent]")

# Final usage summary

print("\n" + "=" * 60)
print("FINAL USAGE SUMMARY")
print("=" * 60)

all_backends = [
    ("Teaching Agent v2", managed),
    ("Bash Only Agent", bash_managed),
    ("No Web Agent", no_web_managed),
    ("Weather Agent", custom_managed),
    ("Search Agent", search_managed),
    ("Data Science Agent", data_managed),
    ("Interruptable Agent", interrupt_managed),
]

total_input = 0
total_output = 0

for name, backend in all_backends:
    info = backend.retrieve_session()
    usage = info.get("usage", {})
    inp = usage.get("input_tokens", backend.total_input_tokens)
    out = usage.get("output_tokens", backend.total_output_tokens)
    total_input += inp
    total_output += out
    print(f"  {name:30s} | in: {inp:6d} | out: {out:6d}")

print(f"  {'TOTAL':30s} | in: {total_input:6d} | out: {total_output:6d}")
print("=" * 60)
