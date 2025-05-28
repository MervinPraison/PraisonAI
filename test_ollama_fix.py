#!/usr/bin/env python3
"""
Test script to verify the Ollama integration fix for Issue #394
Tests environment variable handling in auto.py and cli.py
"""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

# Add source path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai'))

def test_auto_generator_env_vars():
    """Test AutoGenerator with various environment variable combinations"""
    print("Testing AutoGenerator environment variable handling...")
    
    # Test cases with different environment variable combinations
    test_cases = [
        {
            "name": "OPENAI_BASE_URL (Standard OpenAI SDK)",
            "env": {
                "OPENAI_BASE_URL": "http://localhost:11434/v1",
                "OPENAI_MODEL_NAME": "deepseek-r1:14b",
                "OPENAI_API_KEY": "NA"
            },
            "expected_base_url": "http://localhost:11434/v1",
            "expected_model": "deepseek-r1:14b"
        },
        {
            "name": "MODEL_NAME and OPENAI_BASE_URL",
            "env": {
                "MODEL_NAME": "ollama/phi",
                "OPENAI_BASE_URL": "http://localhost:11434/v1",
                "OPENAI_API_KEY": "NA"
            },
            "expected_base_url": "http://localhost:11434/v1",
            "expected_model": "ollama/phi"
        },
        {
            "name": "OLLAMA_API_BASE (Community suggested)",
            "env": {
                "OLLAMA_API_BASE": "http://localhost:11434",
                "MODEL_NAME": "gemma3:4b",
                "OPENAI_API_KEY": "fake-key"
            },
            "expected_base_url": "http://localhost:11434",
            "expected_model": "gemma3:4b"
        },
        {
            "name": "Legacy OPENAI_API_BASE",
            "env": {
                "OPENAI_API_BASE": "http://localhost:11434/v1",
                "OPENAI_MODEL_NAME": "llama2",
                "OPENAI_API_KEY": "not-needed"
            },
            "expected_base_url": "http://localhost:11434/v1",
            "expected_model": "llama2"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n  Testing: {test_case['name']}")
        
        # Clear environment
        old_env = {}
        env_vars = ["MODEL_NAME", "OPENAI_MODEL_NAME", "OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_API_BASE", "OPENAI_API_KEY"]
        for var in env_vars:
            if var in os.environ:
                old_env[var] = os.environ[var]
                del os.environ[var]
        
        try:
            # Set test environment
            for key, value in test_case["env"].items():
                os.environ[key] = value
            
            # Import and test AutoGenerator
            from praisonai.auto import AutoGenerator
            
            # Create a temporary file for agent output
            with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as tmp_file:
                tmp_file.close()
                
                # Create AutoGenerator instance
                generator = AutoGenerator(
                    topic="Test Ollama Integration", 
                    agent_file=tmp_file.name,
                    framework="praisonai"
                )
                
                # Check configuration
                config = generator.config_list[0]
                assert config['base_url'] == test_case['expected_base_url'], \
                    f"Expected base_url {test_case['expected_base_url']}, got {config['base_url']}"
                assert config['model'] == test_case['expected_model'], \
                    f"Expected model {test_case['expected_model']}, got {config['model']}"
                
                print(f"    ✅ base_url: {config['base_url']}")
                print(f"    ✅ model: {config['model']}")
                
                # Clean up
                os.unlink(tmp_file.name)
                
        finally:
            # Restore environment
            for var in env_vars:
                if var in os.environ:
                    del os.environ[var]
            for key, value in old_env.items():
                os.environ[key] = value

def test_cli_env_vars():
    """Test PraisonAI CLI with various environment variable combinations"""
    print("\nTesting PraisonAI CLI environment variable handling...")
    
    test_cases = [
        {
            "name": "OPENAI_BASE_URL with MODEL_NAME",
            "env": {
                "MODEL_NAME": "ollama/deepseek-r1:14b",
                "OPENAI_BASE_URL": "http://localhost:11434/v1",
                "OPENAI_API_KEY": "NA"
            },
            "expected_base_url": "http://localhost:11434/v1",
            "expected_model": "ollama/deepseek-r1:14b"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n  Testing: {test_case['name']}")
        
        # Clear environment
        old_env = {}
        env_vars = ["MODEL_NAME", "OPENAI_MODEL_NAME", "OPENAI_BASE_URL", "OPENAI_API_BASE", "OLLAMA_API_BASE", "OPENAI_API_KEY"]
        for var in env_vars:
            if var in os.environ:
                old_env[var] = os.environ[var]
                del os.environ[var]
        
        try:
            # Set test environment
            for key, value in test_case["env"].items():
                os.environ[key] = value
            
            # Import and test PraisonAI CLI
            from praisonai.cli import PraisonAI
            
            # Create PraisonAI instance
            praison = PraisonAI()
            
            # Check configuration
            config = praison.config_list[0]
            assert config['base_url'] == test_case['expected_base_url'], \
                f"Expected base_url {test_case['expected_base_url']}, got {config['base_url']}"
            assert config['model'] == test_case['expected_model'], \
                f"Expected model {test_case['expected_model']}, got {config['model']}"
            
            print(f"    ✅ base_url: {config['base_url']}")
            print(f"    ✅ model: {config['model']}")
                
        finally:
            # Restore environment
            for var in env_vars:
                if var in os.environ:
                    del os.environ[var]
            for key, value in old_env.items():
                os.environ[key] = value

def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing Ollama Integration Fix for Issue #394")
    print("=" * 60)
    
    try:
        test_auto_generator_env_vars()
        test_cli_env_vars()
        
        print("\n" + "=" * 60)
        print("🎉 All tests passed! Ollama integration fix is working correctly.")
        print("Users can now use these environment variable patterns:")
        print("  - OPENAI_BASE_URL (Standard OpenAI SDK variable)")
        print("  - MODEL_NAME (Community recommended)")
        print("  - OLLAMA_API_BASE (Community recommended)")
        print("  - Legacy OPENAI_API_BASE and OPENAI_MODEL_NAME still work")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()