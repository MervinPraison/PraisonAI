"""Local provider — advanced features: update agent, custom tools, session resume, packages."""
from praisonai import Agent, ManagedAgent, LocalManagedConfig

# ── 1. Create agent ──
managed = ManagedAgent(
    provider="local",
    config=LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful math tutor.",
        name="MathTutor",
    ),
)
agent = Agent(name="tutor", backend=managed)
result = agent.start("What is 17 * 23?", stream=True)
print(f"[1] Created agent: {managed.agent_id} (v{managed.agent_version})")

# ── 2. Update agent ──
managed.update_agent(
    name="Senior Math Tutor",
    system="You are a senior math tutor. Always show your work step by step.",
)
print(f"[2] Updated to v{managed.agent_version}")
result = agent.start("What is 123 + 456?", stream=True)

# ── 3. Custom tool ──
def handle_calculator(tool_name, tool_input):
    expr = tool_input.get("expression", "0")
    try:
        val = eval(expr, {"__builtins__": {}})
    except Exception:
        val = "error"
    print(f"  [Calculator: {expr} = {val}]")
    return str(val)

custom_managed = ManagedAgent(
    provider="local",
    config=LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are an assistant with a calculator tool. Use it for math.",
        name="CalcAgent",
        tools=[
            {
                "type": "custom",
                "name": "calculator",
                "description": "Evaluate a math expression",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Math expression"},
                    },
                    "required": ["expression"],
                },
            },
        ],
    ),
    on_custom_tool=handle_calculator,
)
custom_agent = Agent(name="calc", backend=custom_managed)
print("\n[3] Custom tool agent...")
result = custom_agent.start("Use the calculator to compute 99 * 77", stream=True)

# ── 4. Session resume ──
print("\n[4] Session resume...")
result = agent.start("Remember: my lucky number is 7", stream=True)
ids = managed.save_ids()
print(f"    Saved IDs: {ids}")

resume_managed = ManagedAgent(provider="local", config=LocalManagedConfig(model="gpt-4o-mini"))
resume_managed.restore_ids(ids)
resume_agent = Agent(name="resumed", backend=resume_managed)
result = resume_agent.start("What is my lucky number?", stream=True)
print(f"    Resumed session: {resume_managed.session_id}")

# ── 5. Interrupt ──
print("\n[5] Interrupt demo...")
int_managed = ManagedAgent(
    provider="local",
    config=LocalManagedConfig(model="gpt-4o-mini", system="Be helpful.", name="IntAgent"),
)
int_agent = Agent(name="interruptable", backend=int_managed)
result = int_agent.start("Count from 1 to 5", stream=True)
int_managed.interrupt()
print("    [Interrupt sent]")

# ── 6. Reset session ──
print("\n[6] Reset session...")
managed.reset_session()
result = agent.start("What was my lucky number?", stream=True)
print("    (new session — context lost, expected)")

# ── Usage summary ──
print("\n" + "=" * 50)
info = managed.retrieve_session()
print(f"Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")
print("=" * 50)
print("Done!")
