"""
Integration tests for PraisonAI Memory System.

Tests the complete memory system with real API calls:
- FileMemory with session save/resume
- Context compression with LLM
- Rules management with CLAUDE.md, AGENTS.md, GEMINI.md
- Multi-agent workflows with shared memory

Requires: OPENAI_API_KEY environment variable
"""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from praisonaiagents import Agent
from praisonaiagents.memory import FileMemory, RulesManager


def test_file_memory_with_agent():
    """Test FileMemory integration with Agent."""
    print("\n" + "="*60)
    print("TEST: FileMemory with Agent")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create memory instance
        memory = FileMemory(user_id="test_user", base_path=f"{tmpdir}/memory")
        
        # Add some context
        memory.add_long_term("User prefers Python for backend development", importance=0.9)
        memory.add_long_term("User's name is John", importance=0.95)
        memory.add_short_term("Currently working on an AI project")
        
        # Create agent with memory
        agent = Agent(
            name="Assistant",
            instructions="You are a helpful assistant. Use the memory context to personalize responses.",
            memory=memory,
            output="verbose"
        )
        
        # Test that memory context is included
        response = agent.chat("What do you know about me?")
        print(f"\nAgent Response: {response}")
        
        # Verify memory was used
        assert memory.get_stats()["long_term_count"] >= 2
        print("✓ FileMemory integration test passed")


def test_session_save_resume():
    """Test session save and resume functionality."""
    print("\n" + "="*60)
    print("TEST: Session Save/Resume")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create memory and add context
        memory = FileMemory(user_id="session_test", base_path=f"{tmpdir}/memory")
        memory.add_short_term("Important context from previous session")
        memory.add_short_term("User asked about machine learning")
        memory.add_long_term("User is a data scientist", importance=0.9)
        
        # Save session with conversation history
        conversation = [
            {"role": "user", "content": "Tell me about ML"},
            {"role": "assistant", "content": "Machine learning is..."}
        ]
        session_path = memory.save_session("ml_session", conversation_history=conversation)
        print(f"Session saved to: {session_path}")
        
        # Clear memory
        memory.clear_short_term()
        assert len(memory.get_short_term()) == 0
        
        # Resume session
        session_data = memory.resume_session("ml_session")
        print(f"Session resumed with {len(session_data.get('conversation_history', []))} messages")
        
        # Verify restoration
        assert len(memory.get_short_term()) > 0
        assert len(session_data.get("conversation_history", [])) == 2
        print("✓ Session save/resume test passed")


def test_context_compression_with_llm():
    """Test context compression with real LLM."""
    print("\n" + "="*60)
    print("TEST: Context Compression with LLM")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = FileMemory(
            user_id="compress_test",
            base_path=f"{tmpdir}/memory",
            config={"short_term_limit": 20}
        )
        
        # Add many items to trigger compression
        for i in range(15):
            memory.add_short_term(f"User discussed topic {i}: some detailed context about item {i}")
        
        print(f"Short-term items before compression: {len(memory.get_short_term())}")
        
        # Create LLM function for compression using Agent
        def llm_summarize(prompt):
            from praisonaiagents import Agent
            summarizer = Agent(
                name="Summarizer",
                instructions="You summarize text concisely.",
                output="silent"
            )
            return summarizer.chat(prompt)
        
        # Compress with LLM
        summary = memory.compress(llm_func=llm_summarize, max_items=5)
        print(f"Compression summary: {summary[:100]}...")
        print(f"Short-term items after compression: {len(memory.get_short_term())}")
        
        # Verify compression
        assert len(memory.get_short_term()) <= 5
        assert len(summary) > 0
        print("✓ Context compression test passed")


def test_checkpointing():
    """Test checkpointing with file snapshots."""
    print("\n" + "="*60)
    print("TEST: Checkpointing")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = FileMemory(user_id="checkpoint_test", base_path=f"{tmpdir}/memory")
        
        # Create a test file
        test_file = Path(tmpdir) / "code.py"
        test_file.write_text("def hello():\n    print('Hello')")
        
        # Add memory and create checkpoint
        memory.add_long_term("Original implementation uses hello function")
        checkpoint_id = memory.create_checkpoint("before_refactor", include_files=[str(test_file)])
        print(f"Created checkpoint: {checkpoint_id}")
        
        # Modify file and memory
        test_file.write_text("def greet(name):\n    print(f'Hello {name}')")
        memory.clear_all()
        memory.add_long_term("Refactored to use greet function")
        
        print(f"File after modification: {test_file.read_text()[:30]}...")
        
        # Restore checkpoint
        memory.restore_checkpoint(checkpoint_id, restore_files=True)
        print(f"File after restore: {test_file.read_text()[:30]}...")
        
        # Verify restoration
        assert "hello" in test_file.read_text()
        assert memory.get_stats()["long_term_count"] > 0
        print("✓ Checkpointing test passed")


def test_rules_manager_root_files():
    """Test RulesManager with CLAUDE.md, AGENTS.md, GEMINI.md files."""
    print("\n" + "="*60)
    print("TEST: RulesManager with Root Instruction Files")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create root instruction files
        claude_content = """# Claude Instructions
- Always be helpful and concise
- Use Python for code examples
- Follow best practices
"""
        agents_content = """# Codex Instructions
- Run tests before committing
- Document all functions
"""
        gemini_content = """# Gemini Instructions
- Prefer functional programming
- Use type hints
"""
        praison_content = """---
description: PraisonAI project rules
activation: always
priority: 100
---

# PraisonAI Rules
- Use async when possible
- Follow PEP 8
"""
        
        (Path(tmpdir) / "CLAUDE.md").write_text(claude_content)
        (Path(tmpdir) / "AGENTS.md").write_text(agents_content)
        (Path(tmpdir) / "GEMINI.md").write_text(gemini_content)
        (Path(tmpdir) / "PRAISON.md").write_text(praison_content)
        
        # Create RulesManager
        rules_manager = RulesManager(workspace_path=tmpdir, verbose=1)
        
        # Check stats
        stats = rules_manager.get_stats()
        print(f"Rules stats: {stats}")
        
        # Verify root files were loaded
        assert stats["root_rules"] >= 4, f"Expected at least 4 root rules, got {stats['root_rules']}"
        
        # Get rules by name
        claude_rule = rules_manager.get_rule_by_name("claude")
        agents_rule = rules_manager.get_rule_by_name("agents")
        gemini_rule = rules_manager.get_rule_by_name("gemini")
        praison_rule = rules_manager.get_rule_by_name("praison")
        
        assert claude_rule is not None, "CLAUDE.md not loaded"
        assert agents_rule is not None, "AGENTS.md not loaded"
        assert gemini_rule is not None, "GEMINI.md not loaded"
        assert praison_rule is not None, "PRAISON.md not loaded"
        
        print(f"Claude rule: {claude_rule.description}")
        print(f"Agents rule: {agents_rule.description}")
        print(f"Gemini rule: {gemini_rule.description}")
        print(f"Praison rule: {praison_rule.description}")
        
        # Build context
        context = rules_manager.build_rules_context()
        print(f"\nRules context ({len(context)} chars):")
        print(context[:500] + "..." if len(context) > 500 else context)
        
        assert "helpful" in context.lower() or "python" in context.lower()
        print("✓ RulesManager root files test passed")


def test_multi_agent_with_shared_memory():
    """Test multiple agents sharing memory."""
    print("\n" + "="*60)
    print("TEST: Multi-Agent with Shared Memory")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create shared memory
        shared_memory = FileMemory(user_id="shared", base_path=f"{tmpdir}/memory")
        shared_memory.add_long_term("Project uses Python 3.12", importance=0.9)
        shared_memory.add_long_term("Database is PostgreSQL", importance=0.85)
        
        # Create multiple agents with shared memory
        researcher = Agent(
            name="Researcher",
            role="Research Analyst",
            goal="Research and gather information",
            backstory="Expert at finding and analyzing information",
            memory=shared_memory,
            output="verbose"
        )
        
        writer = Agent(
            name="Writer",
            role="Technical Writer",
            goal="Write clear documentation",
            backstory="Expert at technical writing",
            memory=shared_memory,
            output="verbose"
        )
        
        # Test researcher
        print("\n--- Researcher Agent ---")
        research_response = researcher.chat("What technology stack are we using?")
        print(f"Researcher: {research_response[:200]}...")
        
        # Add finding to memory
        shared_memory.add_short_term("Researcher confirmed: Python 3.12 + PostgreSQL stack")
        
        # Test writer (should see researcher's finding)
        print("\n--- Writer Agent ---")
        writer_response = writer.chat("What should I document about our stack?")
        print(f"Writer: {writer_response[:200]}...")
        
        # Verify shared memory
        stats = shared_memory.get_stats()
        print(f"\nShared memory stats: {stats}")
        assert stats["short_term_count"] >= 1
        assert stats["long_term_count"] >= 2
        print("✓ Multi-agent shared memory test passed")


def test_slash_commands():
    """Test memory slash commands."""
    print("\n" + "="*60)
    print("TEST: Memory Slash Commands")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = FileMemory(user_id="commands_test", base_path=f"{tmpdir}/memory")
        
        # Test /memory add
        result = memory.handle_command("/memory add User prefers dark mode")
        print(f"/memory add: {result}")
        assert result["action"] == "add"
        
        # Test /memory show
        result = memory.handle_command("/memory show")
        print(f"/memory show: {result['stats']}")
        assert result["action"] == "show"
        assert result["stats"]["long_term_count"] >= 1
        
        # Test /memory search
        result = memory.handle_command("/memory search dark mode")
        print(f"/memory search: {len(result.get('results', []))} results")
        assert result["action"] == "search"
        
        # Test /memory save
        result = memory.handle_command("/memory save test_session")
        print(f"/memory save: {result}")
        assert result["action"] == "save"
        
        # Test /memory sessions
        result = memory.handle_command("/memory sessions")
        print(f"/memory sessions: {len(result.get('sessions', []))} sessions")
        assert result["action"] == "sessions"
        
        # Test /memory checkpoint
        result = memory.handle_command("/memory checkpoint test_cp")
        print(f"/memory checkpoint: {result}")
        assert result["action"] == "checkpoint"
        
        # Test /memory checkpoints
        result = memory.handle_command("/memory checkpoints")
        print(f"/memory checkpoints: {len(result.get('checkpoints', []))} checkpoints")
        assert result["action"] == "checkpoints"
        
        # Test /memory help
        result = memory.handle_command("/memory help")
        print(f"/memory help: {len(result.get('commands', {}))} commands")
        assert result["action"] == "help"
        assert len(result["commands"]) >= 10
        
        print("✓ Slash commands test passed")


def test_agent_with_rules():
    """Test Agent with RulesManager integration."""
    print("\n" + "="*60)
    print("TEST: Agent with Rules Integration")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create PRAISON.md in workspace
        praison_rules = """# Project Rules
- Always respond in a friendly manner
- Use bullet points for lists
- Keep responses concise
"""
        (Path(tmpdir) / "PRAISON.md").write_text(praison_rules)
        
        # Change to temp directory to test rules discovery
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        
        try:
            # Create agent (should auto-discover rules)
            agent = Agent(
                name="RulesAgent",
                instructions="You are a helpful assistant.",
                output="verbose"
            )
            
            # Check if rules were loaded
            if agent._rules_manager:
                stats = agent._rules_manager.get_stats()
                print(f"Rules discovered: {stats}")
                
                # Get rules context
                context = agent.get_rules_context()
                print(f"Rules context: {context[:200]}..." if context else "No rules context")
            
            # Test agent response
            response = agent.chat("List 3 benefits of Python")
            print(f"\nAgent response: {response[:300]}...")
            
            print("✓ Agent with rules test passed")
        finally:
            os.chdir(original_cwd)


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("PRAISONAI MEMORY SYSTEM - INTEGRATION TESTS")
    print("="*60)
    
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY not set. Some tests may fail.")
    
    tests = [
        ("FileMemory with Agent", test_file_memory_with_agent),
        ("Session Save/Resume", test_session_save_resume),
        ("Context Compression", test_context_compression_with_llm),
        ("Checkpointing", test_checkpointing),
        ("RulesManager Root Files", test_rules_manager_root_files),
        ("Multi-Agent Shared Memory", test_multi_agent_with_shared_memory),
        ("Slash Commands", test_slash_commands),
        ("Agent with Rules", test_agent_with_rules),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
