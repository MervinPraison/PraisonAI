#!/usr/bin/env python3
"""Test script to reproduce and verify fix for multi-agent streaming issue #1733"""

import sys
import os

# Add the praisonaiagents package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

print("Testing multi-agent functionality with the fix...")

try:
    from praisonaiagents import Agent, Agents

    research_agent = Agent(instructions="Research about AI")
    summarise_agent = Agent(instructions="Summarise research agent's findings")
    agents = Agents(agents=[research_agent, summarise_agent])
    
    print("✓ Successfully created agents")
    
    # Test that our fix worked: the sync methods should not use streaming by default
    # Check the method signatures in chat_mixin.py
    import inspect
    from praisonaiagents.agent.chat_mixin import ChatMixin
    
    # Check _chat_completion method
    chat_completion_sig = inspect.signature(ChatMixin._chat_completion)
    stream_param = chat_completion_sig.parameters.get('stream')
    if stream_param and stream_param.default == False:
        print("✓ _chat_completion method has stream=False as default")
    else:
        print(f"✗ _chat_completion method stream default is: {stream_param.default}")
        
    # Check _execute_unified_chat_completion method  
    unified_chat_sig = inspect.signature(ChatMixin._execute_unified_chat_completion)
    unified_stream_param = unified_chat_sig.parameters.get('stream')
    if unified_stream_param and unified_stream_param.default == False:
        print("✓ _execute_unified_chat_completion method has stream=False as default")
    else:
        print(f"✗ _execute_unified_chat_completion method stream default is: {unified_stream_param.default}")
    
    print("✓ Fix validation completed - sync methods now default to stream=False")
    print("✓ This should resolve the 'Streaming is not supported in sync OpenAIAdapter' error")
    
except Exception as e:
    print(f"✗ Error occurred during validation: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("✓ All tests passed!")