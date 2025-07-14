#!/usr/bin/env python3
"""
Test script to verify the duplicate callback fix for issue #878
This tests that display_interaction is only called once per LLM response
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents.llm.llm import LLM
from unittest.mock import patch, MagicMock
import json

# Track display_interaction calls
display_calls = []

def mock_display_interaction(prompt, response, markdown=True, generation_time=0, console=None):
    """Mock display_interaction to track calls"""
    display_calls.append({
        'prompt': prompt,
        'response': response,
        'markdown': markdown,
        'generation_time': generation_time
    })
    print(f"[DISPLAY] {prompt[:50]}... -> {response[:50]}...")

def test_single_display_no_tools():
    """Test that display_interaction is called only once without tools"""
    global display_calls
    display_calls = []
    
    with patch('praisonaiagents.llm.llm.display_interaction', side_effect=mock_display_interaction):
        with patch('litellm.completion') as mock_completion:
            # Mock streaming response
            mock_completion.return_value = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content="!"))])
            ]
            
            llm = LLM(model="gpt-4o-mini", verbose=False)
            response = llm.get_response(
                prompt="Test prompt",
                verbose=True,
                stream=True
            )
            
            print(f"\nResponse: {response}")
            print(f"Display calls: {len(display_calls)}")
            
            assert len(display_calls) == 1, f"Expected 1 display call, got {len(display_calls)}"
            assert response == "Hello world!"

def test_single_display_with_reasoning():
    """Test that display_interaction is called only once with reasoning steps"""
    global display_calls
    display_calls = []
    
    with patch('praisonaiagents.llm.llm.display_interaction', side_effect=mock_display_interaction):
        with patch('litellm.completion') as mock_completion:
            # Mock non-streaming response with reasoning
            mock_completion.return_value = {
                "choices": [{
                    "message": {
                        "content": "The answer is 42",
                        "provider_specific_fields": {
                            "reasoning_content": "Let me think about this..."
                        }
                    }
                }]
            }
            
            llm = LLM(model="o1-preview", verbose=False, reasoning_steps=True)
            response = llm.get_response(
                prompt="What is the meaning of life?",
                verbose=True,
                stream=False,
                reasoning_steps=True
            )
            
            print(f"\nResponse: {response}")
            print(f"Display calls: {len(display_calls)}")
            
            assert len(display_calls) == 1, f"Expected 1 display call, got {len(display_calls)}"

def test_single_display_with_self_reflection():
    """Test that display_interaction is called appropriately with self-reflection"""
    global display_calls
    display_calls = []
    
    with patch('praisonaiagents.llm.llm.display_interaction', side_effect=mock_display_interaction):
        with patch('praisonaiagents.main.display_self_reflection'):
            with patch('litellm.completion') as mock_completion:
                # First call - initial response
                # Second call - reflection
                # Third call - regenerated response
                call_count = 0
                def mock_streaming(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    
                    if call_count == 1:
                        # Initial response
                        return [
                            MagicMock(choices=[MagicMock(delta=MagicMock(content="Initial"))]),
                            MagicMock(choices=[MagicMock(delta=MagicMock(content=" response"))])
                        ]
                    elif call_count == 2:
                        # Reflection
                        reflection = {"reflection": "Could be better", "satisfactory": "no"}
                        return [
                            MagicMock(choices=[MagicMock(delta=MagicMock(content=json.dumps(reflection)))])
                        ]
                    else:
                        # Final response
                        return [
                            MagicMock(choices=[MagicMock(delta=MagicMock(content="Better"))]),
                            MagicMock(choices=[MagicMock(delta=MagicMock(content=" response"))])
                        ]
                
                mock_completion.side_effect = mock_streaming
                
                llm = LLM(model="gpt-4o-mini", verbose=False, self_reflect=True, min_reflect=1, max_reflect=2)
                response = llm.get_response(
                    prompt="Test prompt",
                    verbose=True,
                    stream=True,
                    self_reflect=True,
                    min_reflect=1,
                    max_reflect=2
                )
                
                print(f"\nResponse: {response}")
                print(f"Display calls: {len(display_calls)}")
                
                # Should display only the final response
                assert len(display_calls) == 1, f"Expected 1 display call, got {len(display_calls)}"
                assert response == "Better response"

def test_async_single_display():
    """Test async version also prevents duplicate displays"""
    global display_calls
    display_calls = []
    
    import asyncio
    
    async def run_test():
        with patch('praisonaiagents.llm.llm.display_interaction', side_effect=mock_display_interaction):
            with patch('litellm.acompletion') as mock_acompletion:
                # Mock async streaming response
                async def async_generator():
                    yield MagicMock(choices=[MagicMock(delta=MagicMock(content="Async"))])
                    yield MagicMock(choices=[MagicMock(delta=MagicMock(content=" response"))])
                
                mock_acompletion.return_value = async_generator()
                
                llm = LLM(model="gpt-4o-mini", verbose=False)
                response = await llm.get_response_async(
                    prompt="Test async",
                    verbose=True,
                    stream=True
                )
                
                print(f"\nAsync Response: {response}")
                print(f"Display calls: {len(display_calls)}")
                
                assert len(display_calls) == 1, f"Expected 1 display call, got {len(display_calls)}"
                assert response == "Async response"
    
    asyncio.run(run_test())

if __name__ == "__main__":
    print("Testing duplicate callback fix for issue #878...\n")
    
    try:
        print("1. Testing single display without tools...")
        test_single_display_no_tools()
        print("✓ PASSED\n")
        
        print("2. Testing single display with reasoning...")
        test_single_display_with_reasoning()
        print("✓ PASSED\n")
        
        print("3. Testing single display with self-reflection...")
        test_single_display_with_self_reflection()
        print("✓ PASSED\n")
        
        print("4. Testing async single display...")
        test_async_single_display()
        print("✓ PASSED\n")
        
        print("All tests passed! The duplicate callback issue is fixed.")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)