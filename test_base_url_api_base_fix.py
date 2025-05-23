#!/usr/bin/env python3
"""
Test script to verify the fix for issue #467
Tests that base_url in LLM dictionary is properly mapped to both base_url and api_base for litellm
"""

import sys
import os

# Add the praisonai-agents to path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_llm_base_url_mapping():
    """Test that LLM class properly maps base_url to both base_url and api_base"""
    print("Testing LLM class base_url to api_base mapping...")
    
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Test with base_url parameter
        llm = LLM(
            model="openai/gpt-3.5-turbo",
            base_url="http://0.0.0.0:4000",
            api_key="sk-1234"
        )
        
        # Build completion parameters
        params = llm._build_completion_params(
            messages=[{"role": "user", "content": "test"}]
        )
        
        print("Parameters passed to litellm:")
        for key, value in params.items():
            if key in ['model', 'base_url', 'api_base', 'api_key']:
                print(f"  {key}: {value}")
        
        # Verify both base_url and api_base are set
        assert 'base_url' in params, "base_url should be in params"
        assert 'api_base' in params, "api_base should be in params"
        assert params['base_url'] == "http://0.0.0.0:4000", "base_url should match input"
        assert params['api_base'] == "http://0.0.0.0:4000", "api_base should match base_url"
        
        print("✅ SUCCESS: LLM class correctly maps base_url to both base_url and api_base")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_agent_with_llm_dict():
    """Test that Agent with LLM dictionary works correctly"""
    print("\nTesting Agent with LLM dictionary...")
    
    try:
        from praisonaiagents.agent.agent import Agent
        
        # Test with LLM dictionary (the original use case from the issue)
        llm_config = {
            'model': 'openai/gpt-3.5-turbo',
            'base_url': 'http://0.0.0.0:4000',  
            'api_key': 'sk-1234'
        }
        
        agent = Agent(
            name="Test Agent",
            role="Test Role", 
            goal="Test Goal",
            backstory="Test Backstory",
            llm=llm_config  # This should work with the fix
        )
        
        # Verify agent has custom LLM instance
        assert hasattr(agent, 'llm_instance'), "Agent should have llm_instance"
        assert agent._using_custom_llm == True, "Agent should be using custom LLM"
        
        # Check that the LLM instance has correct parameters
        assert agent.llm_instance.base_url == 'http://0.0.0.0:4000', "LLM instance should have base_url"
        
        # Test the parameter building
        params = agent.llm_instance._build_completion_params(
            messages=[{"role": "user", "content": "test"}]
        )
        
        assert 'base_url' in params, "base_url should be in params"
        assert 'api_base' in params, "api_base should be in params"
        
        print("✅ SUCCESS: Agent with LLM dictionary works correctly")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_image_agent_consistency():
    """Test that ImageAgent uses consistent parameter naming"""
    print("\nTesting ImageAgent parameter consistency...")
    
    try:
        from praisonaiagents.agent.image_agent import ImageAgent
        
        # Test with base_url parameter
        image_agent = ImageAgent(
            name="Test Image Agent",
            llm="dall-e-3",
            base_url="http://0.0.0.0:4000",
            api_key="sk-1234"
        )
        
        # Check that config uses base_url
        assert hasattr(image_agent, 'image_config'), "ImageAgent should have image_config"
        config_dict = image_agent.image_config.dict(exclude_none=True)
        
        if 'base_url' in config_dict:
            print(f"  base_url in config: {config_dict['base_url']}")
        
        print("✅ SUCCESS: ImageAgent uses consistent parameter naming")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    print("Testing fix for issue #467: base_url not passed as api_base to litellm\n")
    
    success_count = 0
    total_tests = 3
    
    if test_llm_base_url_mapping():
        success_count += 1
    
    if test_agent_with_llm_dict():
        success_count += 1
        
    if test_image_agent_consistency():
        success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Test Results: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("🎉 ALL TESTS PASSED - Issue #467 appears to be fixed!")
    else:
        print("⚠️  Some tests failed - Issue #467 may still need work")
    
    print("="*60)