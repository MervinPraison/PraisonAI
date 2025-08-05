#!/usr/bin/env python3
"""
Test script to verify Qwen XML tool call parsing functionality.
This test simulates the Qwen XML response format and verifies parsing.
"""

import json
import re
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def test_qwen_xml_parsing():
    """Test the XML parsing logic for Qwen tool calls"""
    
    # Simulate a Qwen response with XML tool call format
    sample_response = '''To list all the pods in the test namespace, I'll use the kubectl_get tool:

<tool_call>
{"name": "kubectl_get", "arguments": {"resourceType": "pods", "namespace": "test", "output": "wide"}}
</tool_call>

This will show all pods in the test namespace with wide output format.'''
    
    # Test the XML parsing logic (same as implemented in llm.py)
    tool_call_pattern = r'<tool_call>\s*({.*?})\s*</tool_call>'
    matches = re.findall(tool_call_pattern, sample_response, re.DOTALL)
    
    print("Testing Qwen XML Tool Call Parsing")
    print("=" * 50)
    print(f"Sample response:\n{sample_response}")
    print("\n" + "="*50)
    
    if matches:
        tool_calls = []
        for idx, match in enumerate(matches):
            try:
                # Parse the JSON inside the XML tag
                tool_json = json.loads(match.strip())
                if isinstance(tool_json, dict) and "name" in tool_json:
                    tool_call = {
                        "id": f"tool_test_{idx}",
                        "type": "function",
                        "function": {
                            "name": tool_json["name"],
                            "arguments": json.dumps(tool_json.get("arguments", {}))
                        }
                    }
                    tool_calls.append(tool_call)
                    print(f"Successfully parsed tool call {idx + 1}:")
                    print(f"  Function: {tool_json['name']}")
                    print(f"  Arguments: {tool_json.get('arguments', {})}")
                    print(f"  Standard format: {json.dumps(tool_call, indent=2)}")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Could not parse tool call from XML: {e}")
                continue
        
        if tool_calls:
            print(f"\n✅ SUCCESS: Parsed {len(tool_calls)} tool call(s) from Qwen XML format")
            print(f"Tool calls ready for execution: {json.dumps(tool_calls, indent=2)}")
        else:
            print("❌ FAILED: No valid tool calls parsed")
    else:
        print("❌ FAILED: No XML tool call patterns found")

def test_qwen_provider_detection():
    """Test Qwen provider detection logic"""
    
    # Test various model name patterns
    test_models = [
        "openai/Qwen/Qwen2.5-VL-7B-Instruct",
        "openai/Qwen/Qwen2.5-7B-Instruct", 
        "qwen2.5-72b-instruct",
        "Qwen2-VL-7B-Instruct",
        "gpt-4o-mini",  # Should NOT be detected as Qwen
        "claude-3-5-sonnet"  # Should NOT be detected as Qwen
    ]
    
    def _is_qwen_provider(model: str) -> bool:
        """Test implementation of Qwen provider detection"""
        if not model:
            return False
        
        # Direct qwen/ prefix or Qwen in model name
        model_lower = model.lower()
        if any(pattern in model_lower for pattern in ["qwen", "qwen2", "qwen2.5"]):
            return True
        
        # OpenAI-compatible API serving Qwen models
        if "openai/" in model and any(pattern in model_lower for pattern in ["qwen", "qwen2", "qwen2.5"]):
            return True
            
        return False
    
    print("\nTesting Qwen Provider Detection")
    print("=" * 50)
    
    for model in test_models:
        is_qwen = _is_qwen_provider(model)
        expected = "qwen" in model.lower()
        status = "✅" if is_qwen == expected else "❌"
        print(f"{status} {model}: {is_qwen} (expected: {expected})")

if __name__ == "__main__":
    test_qwen_xml_parsing()
    test_qwen_provider_detection()
    print("\n" + "="*50)
    print("Test completed!")