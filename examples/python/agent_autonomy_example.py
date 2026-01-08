"""
Agent-Centric Autonomy Example.

Demonstrates the new agent-centric autonomy features in PraisonAI Agents:
- Agent(autonomy=True) for enabling autonomy
- Progressive escalation stages (DIRECT, HEURISTIC, PLANNED, AUTONOMOUS)
- Doom loop detection and recovery
- Verification hooks
- Subagent delegation
"""

from praisonaiagents import Agent


def example_basic_autonomy():
    """Basic autonomy example - simple question."""
    print("\n" + "="*60)
    print("Example 1: Basic Autonomy - Simple Question")
    print("="*60)
    
    agent = Agent(
        instructions="You are a helpful coding assistant.",
        autonomy=True,
    )
    
    # Analyze a simple question
    prompt = "What is Python?"
    signals = agent.analyze_prompt(prompt)
    stage = agent.get_recommended_stage(prompt)
    
    print(f"Prompt: {prompt}")
    print(f"Detected signals: {signals}")
    print(f"Recommended stage: {stage}")
    
    # For simple questions, stage should be "direct"
    assert stage == "direct", f"Expected 'direct', got '{stage}'"
    print("✓ Simple question correctly identified as DIRECT stage")


def example_file_reference():
    """File reference detection example."""
    print("\n" + "="*60)
    print("Example 2: File Reference Detection")
    print("="*60)
    
    agent = Agent(
        instructions="You are a code reviewer.",
        autonomy=True,
    )
    
    prompt = "Read the main.py file and explain what it does"
    signals = agent.analyze_prompt(prompt)
    stage = agent.get_recommended_stage(prompt)
    
    print(f"Prompt: {prompt}")
    print(f"Detected signals: {signals}")
    print(f"Recommended stage: {stage}")
    
    assert "file_references" in signals, "Expected file_references signal"
    assert stage == "heuristic", f"Expected 'heuristic', got '{stage}'"
    print("✓ File reference correctly identified as HEURISTIC stage")


def example_edit_intent():
    """Edit intent detection example."""
    print("\n" + "="*60)
    print("Example 3: Edit Intent Detection")
    print("="*60)
    
    agent = Agent(
        instructions="You are a code editor.",
        autonomy=True,
    )
    
    prompt = "Edit the config.py file to add logging support"
    signals = agent.analyze_prompt(prompt)
    stage = agent.get_recommended_stage(prompt)
    
    print(f"Prompt: {prompt}")
    print(f"Detected signals: {signals}")
    print(f"Recommended stage: {stage}")
    
    assert "edit_intent" in signals, "Expected edit_intent signal"
    assert stage == "planned", f"Expected 'planned', got '{stage}'"
    print("✓ Edit intent correctly identified as PLANNED stage")


def example_multi_step_task():
    """Multi-step task detection example."""
    print("\n" + "="*60)
    print("Example 4: Multi-Step Task Detection")
    print("="*60)
    
    agent = Agent(
        instructions="You are a software architect.",
        autonomy=True,
    )
    
    prompt = """First analyze the codebase structure, 
    then refactor the authentication module, 
    and finally add comprehensive tests."""
    
    signals = agent.analyze_prompt(prompt)
    stage = agent.get_recommended_stage(prompt)
    
    print(f"Prompt: {prompt[:50]}...")
    print(f"Detected signals: {signals}")
    print(f"Recommended stage: {stage}")
    
    assert "multi_step" in signals, "Expected multi_step signal"
    assert stage == "autonomous", f"Expected 'autonomous', got '{stage}'"
    print("✓ Multi-step task correctly identified as AUTONOMOUS stage")


def example_custom_config():
    """Custom autonomy configuration example."""
    print("\n" + "="*60)
    print("Example 5: Custom Autonomy Configuration")
    print("="*60)
    
    agent = Agent(
        instructions="You are a careful code reviewer.",
        autonomy={
            "max_iterations": 50,
            "doom_loop_threshold": 5,
            "auto_escalate": True,
            "checkpoint_on_write": True,
        },
    )
    
    print(f"Autonomy enabled: {agent.autonomy_enabled}")
    print(f"Max iterations: {agent.autonomy_config.get('max_iterations')}")
    print(f"Doom loop threshold: {agent.autonomy_config.get('doom_loop_threshold')}")
    print(f"Checkpoint on write: {agent.autonomy_config.get('checkpoint_on_write')}")
    
    assert agent.autonomy_enabled == True
    assert agent.autonomy_config.get("max_iterations") == 50
    print("✓ Custom configuration applied correctly")


def example_doom_loop_detection():
    """Doom loop detection example."""
    print("\n" + "="*60)
    print("Example 6: Doom Loop Detection")
    print("="*60)
    
    agent = Agent(
        instructions="You are a test agent.",
        autonomy={"doom_loop_threshold": 3},
    )
    
    # Simulate repeated actions
    print("Simulating repeated actions...")
    for i in range(3):
        agent._record_action("read_file", {"path": "test.py"}, "content", True)
        print(f"  Action {i+1}: read_file test.py")
    
    is_doom_loop = agent._is_doom_loop()
    print(f"Doom loop detected: {is_doom_loop}")
    
    assert is_doom_loop == True, "Expected doom loop to be detected"
    print("✓ Doom loop correctly detected after repeated actions")
    
    # Reset and verify
    agent._reset_doom_loop()
    is_doom_loop_after_reset = agent._is_doom_loop()
    print(f"After reset: {is_doom_loop_after_reset}")
    assert is_doom_loop_after_reset == False
    print("✓ Doom loop correctly reset")


def example_verification_hooks():
    """Verification hooks example."""
    print("\n" + "="*60)
    print("Example 7: Verification Hooks")
    print("="*60)
    
    # Create a simple mock verification hook
    class MockTestRunner:
        name = "pytest"
        
        def run(self, context=None):
            return {"success": True, "output": "All 10 tests passed"}
    
    agent = Agent(
        instructions="You are a test-driven developer.",
        autonomy=True,
        verification_hooks=[MockTestRunner()],
    )
    
    print(f"Verification hooks registered: {len(agent._verification_hooks)}")
    
    # Run verification hooks
    results = agent._run_verification_hooks()
    print(f"Verification results: {results}")
    
    assert len(results) == 1
    assert results[0]["success"] == True
    print("✓ Verification hooks executed correctly")


def example_subagent_delegation():
    """Subagent delegation example."""
    print("\n" + "="*60)
    print("Example 8: Subagent Delegation")
    print("="*60)
    
    agent = Agent(
        instructions="You are a project manager.",
        autonomy=True,
    )
    
    # Check delegate method exists
    assert hasattr(agent, "delegate"), "Agent should have delegate method"
    assert callable(agent.delegate), "delegate should be callable"
    
    # Check _create_subagent method
    subagent = agent._create_subagent("explorer")
    print(f"Created subagent: {subagent.name}")
    print(f"Subagent instructions: {subagent.instructions[:50]}...")
    
    assert "subagent_explorer" in subagent.name
    print("✓ Subagent delegation works correctly")


def example_explorer_profile():
    """Explorer profile example."""
    print("\n" + "="*60)
    print("Example 9: Explorer Profile (Read-Only)")
    print("="*60)
    
    from praisonaiagents.agents.profiles import BUILTIN_PROFILES, get_profile
    
    explorer = get_profile("explorer")
    
    print(f"Profile name: {explorer.name}")
    print(f"Description: {explorer.description[:60]}...")
    print(f"Tools: {explorer.tools}")
    print(f"Read-only metadata: {explorer.metadata.get('read_only')}")
    
    # Verify explorer is read-only
    write_tools = {"write_file", "delete_file", "bash", "shell"}
    has_write_tools = any(tool in write_tools for tool in explorer.tools)
    
    assert not has_write_tools, "Explorer should not have write tools"
    assert explorer.metadata.get("read_only") == True
    print("✓ Explorer profile is correctly read-only")


def example_run_autonomous_method():
    """run_autonomous method example (without actual LLM call)."""
    print("\n" + "="*60)
    print("Example 10: run_autonomous Method")
    print("="*60)
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        autonomy=True,
    )
    
    # Verify method exists
    assert hasattr(agent, "run_autonomous"), "Agent should have run_autonomous method"
    assert callable(agent.run_autonomous), "run_autonomous should be callable"
    
    print("✓ run_autonomous method exists and is callable")
    print("  (Skipping actual execution to avoid LLM API calls)")


def main():
    """Run all examples."""
    print("\n" + "#"*60)
    print("# Agent-Centric Autonomy Examples")
    print("#"*60)
    
    try:
        example_basic_autonomy()
        example_file_reference()
        example_edit_intent()
        example_multi_step_task()
        example_custom_config()
        example_doom_loop_detection()
        example_verification_hooks()
        example_subagent_delegation()
        example_explorer_profile()
        example_run_autonomous_method()
        
        print("\n" + "="*60)
        print("All examples completed successfully! ✓")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
