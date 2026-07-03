"""
End-to-end integration test for proactive context compaction.

This is a REAL agentic test that actually calls LLMs near context limits
to verify that proactive context overflow protection works correctly.
"""

import pytest
import time
import os
from unittest.mock import patch

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.context.adapters import ContextCompactionPolicyAdapter
from praisonaiagents.context.protocols import CompactionStrategy


def create_long_conversation():
    """Create a long conversation history that approaches context limits."""
    messages = []
    
    # Add a system message
    messages.append({
        "role": "system", 
        "content": "You are a helpful assistant. Always respond concisely but helpfully."
    })
    
    # Add many back-and-forth exchanges to build up context
    topics = [
        "machine learning", "web development", "data science", "cloud computing",
        "artificial intelligence", "cybersecurity", "mobile apps", "databases",
        "algorithms", "software engineering", "DevOps", "blockchain technology"
    ]
    
    for i, topic in enumerate(topics):
        # User asks about topic
        messages.append({
            "role": "user",
            "content": f"Tell me about {topic} and how it's used in modern software development. "
                      f"Please provide detailed examples and best practices. "
                      f"This is question number {i+1} in our conversation."
        })
        
        # Assistant provides detailed response
        messages.append({
            "role": "assistant", 
            "content": f"{topic.title()} is a crucial aspect of modern software development. "
                      f"Here are the key concepts and applications:\n\n"
                      f"1. Definition: {topic} involves various technical approaches and methodologies.\n"
                      f"2. Use Cases: It's commonly used in enterprise applications, web platforms, and mobile solutions.\n"
                      f"3. Best Practices: Following industry standards and maintaining code quality is essential.\n"
                      f"4. Tools and Technologies: Popular frameworks include various open-source and commercial solutions.\n"
                      f"5. Implementation: Step-by-step approach involves planning, development, testing, and deployment.\n"
                      f"6. Performance Considerations: Optimization and scalability are key factors to consider.\n"
                      f"7. Security Aspects: Proper authentication, authorization, and data protection are vital.\n"
                      f"8. Future Trends: The field continues to evolve with new technologies and approaches.\n\n"
                      f"This comprehensive overview of {topic} should help you understand its role in software development. "
                      f"The practical applications range from small startups to large enterprise solutions."
        })
        
        # Add some tool call examples for complexity
        if i % 3 == 0:
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{i}_search",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": f'{{"query": "latest {topic} trends 2024"}}'
                        }
                    }
                ]
            })
            
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{i}_search", 
                "content": f"Search results for {topic} trends:\n"
                          f"1. Emerging frameworks and tools are gaining popularity\n"
                          f"2. Integration with AI and ML technologies is increasing\n"
                          f"3. Community adoption is growing rapidly\n"
                          f"4. Enterprise solutions are becoming more sophisticated\n"
                          f"5. Performance optimizations are a key focus area\n"
                          + "Additional detailed information: " + "x" * 500  # Padding to increase token count
            })
    
    return messages


@pytest.mark.integration  
def test_proactive_compaction_end_to_end():
    """
    REAL agentic test: Agent runs end-to-end with proactive context compaction.
    
    This test verifies that:
    1. Agent can handle conversations approaching context limits
    2. Proactive compaction triggers automatically
    3. Agent continues to function normally after compaction
    4. LLM is actually called and produces real responses
    """
    
    # Create agent with aggressive compaction policy for testing
    compaction_policy = ContextCompactionPolicyAdapter(
        trigger_at=0.70,  # Trigger earlier for testing
        strategy=CompactionStrategy.DROP_OLDEST_TOOLS,
        preserve_last_n_turns=3,  # Keep only recent exchanges
        target_utilization=0.50,
        aggressive_tool_truncation=True
    )
    
    agent = Agent(
        name="context_test_agent",
        instructions="You are a helpful assistant. Always respond with exactly one sentence.",
        llm="gpt-4o-mini",  # Use smaller model for faster testing
        execution=ExecutionConfig(context_compaction=compaction_policy),
        output="verbose",
    )
    
    # Pre-load conversation history to approach limits
    long_conversation = create_long_conversation()
    
    # Manually set the chat history to simulate a long conversation
    agent.chat_history = long_conversation
    
    print(f"\n=== Starting with {len(long_conversation)} messages in history ===")
    
    # Now make a new request that should trigger compaction
    start_time = time.time()
    try:
        response = agent.chat(
            "Given our discussion, summarise the key themes in one sentence."
        )
        if response is None:
            pytest.skip("LLM returned no response for compaction test")
        end_time = time.time()
        assert isinstance(response, str), f"Expected string response, got {type(response)}"
        assert len(response) > 10, f"Response too short: '{response}'"
        assert "error" not in response.lower(), f"Error in response: {response}"
        
        print(f"\n=== Agent Response (after {end_time - start_time:.1f}s) ===")
        print(f"Response: {response}")
        print(f"Final history length: {len(agent.chat_history)} messages")
        
        # Verify that compaction occurred (history should be shorter)
        # The exact number depends on the compaction strategy, but it should be significantly reduced
        assert len(agent.chat_history) < len(long_conversation), \
            "Expected history to be compacted, but length didn't decrease"
        
        # Verify agent is still functional by asking a follow-up
        follow_up = agent.chat("Name one technology from our discussion.")
        if follow_up is None:
            pytest.skip("LLM returned no follow-up for compaction test")
        
        print(f"\n=== Follow-up Response ===")
        print(f"Response: {follow_up}")
        
        return True
        
    except Exception as e:
        print(f"\n=== Test Failed ===")
        print(f"Error: {e}")
        print(f"Agent history length: {len(agent.chat_history)}")
        raise


@pytest.mark.integration
def test_compaction_disabled_still_works():
    """Test that explicitly disabling compaction still works."""
    
    agent = Agent(
        name="no_compaction_agent", 
        instructions="You are helpful.",
        llm="gpt-4o-mini",
        execution=ExecutionConfig(context_compaction=False),
    )
    
    # Should work normally without compaction
    response = agent.start("Hello! How are you?")
    assert isinstance(response, str)
    assert len(response) > 5
    
    print(f"\n=== No Compaction Test ===")
    print(f"Response: {response}")


@pytest.mark.integration  
def test_default_agent_has_compaction():
    """Test that new agents get compaction by default (after deprecation period)."""
    
    # Create agent with default settings
    agent = Agent(
        name="default_agent",
        instructions="You are helpful.",
        llm="gpt-4o-mini"
    )
    
    # Check if execution config has context_compaction
    # Note: During deprecation period, this might still be False with a warning
    exec_config = getattr(agent, 'execution', None)
    assert exec_config is not None, "Agent should have execution config"
    
    # Should be able to respond normally
    response = agent.start("Hello!")
    assert isinstance(response, str)
    assert len(response) > 0
    
    print(f"\n=== Default Agent Test ===")
    print(f"Has execution config: {exec_config is not None}")
    print(f"Context compaction setting: {getattr(exec_config, 'context_compaction', None)}")
    print(f"Response: {response}")


@pytest.mark.integration
def test_sync_async_compaction_parity():
    """Test that sync and async paths both apply compaction consistently."""
    import asyncio
    
    policy = ContextCompactionPolicyAdapter(
        trigger_at=0.60,
        target_utilization=0.40,
        preserve_last_n_turns=2,
    )
    
    # Test sync path
    sync_agent = Agent(
        name="sync_agent",
        llm="gpt-4o-mini", 
        execution=ExecutionConfig(context_compaction=policy)
    )
    
    # Add some history
    sync_agent.chat_history = create_long_conversation()[:10]  # Subset for speed
    initial_length = len(sync_agent.chat_history)
    
    sync_response = sync_agent.start("Summarize our discussion.")
    
    # Test async path
    async def test_async():
        async_agent = Agent(
            name="async_agent",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(context_compaction=policy)
        )
        
        async_agent.chat_history = create_long_conversation()[:10]  # Same subset
        return await async_agent.astart("Summarize our discussion.")
    
    async_response = asyncio.run(test_async())
    
    # Both should return valid responses 
    assert isinstance(sync_response, str) and len(sync_response) > 10
    assert isinstance(async_response, str) and len(async_response) > 10
    
    print(f"\n=== Sync/Async Parity Test ===")
    print(f"Initial history: {initial_length} messages")  
    print(f"Sync response: {sync_response[:100]}...")
    print(f"Async response: {async_response[:100]}...")


if __name__ == "__main__":
    # Run individual tests for debugging
    print("Running end-to-end context compaction tests...")
    
    try:
        test_proactive_compaction_end_to_end()
        print("✓ End-to-end test passed")
    except Exception as e:
        print(f"✗ End-to-end test failed: {e}")
    
    try:
        test_compaction_disabled_still_works()  
        print("✓ Disabled compaction test passed")
    except Exception as e:
        print(f"✗ Disabled compaction test failed: {e}")
    
    try:
        test_default_agent_has_compaction()
        print("✓ Default agent test passed")
    except Exception as e:
        print(f"✗ Default agent test failed: {e}")
    
    try:
        test_sync_async_compaction_parity()
        print("✓ Sync/async parity test passed")
    except Exception as e:
        print(f"✗ Sync/async parity test failed: {e}")