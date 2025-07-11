#!/usr/bin/env python3
"""
Test script for CrewAI advanced features in PraisonAI
"""

import os
import yaml
import tempfile
from praisonai import PraisonAI

def test_basic_crewai():
    """Test basic CrewAI functionality"""
    print("Testing basic CrewAI functionality...")
    
    config = """
framework: "crewai"
topic: "AI Testing"
roles:
  tester:
    role: "Tester"
    goal: "Test the system"
    backstory: "Expert tester"
    tasks:
      test_task:
        description: "Perform a simple test"
        expected_output: "Test results"
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config)
        temp_file = f.name
    
    try:
        praisonai = PraisonAI(agent_file=temp_file, framework="crewai")
        print("✅ Basic CrewAI configuration loaded successfully")
    except Exception as e:
        print(f"❌ Basic CrewAI test failed: {e}")
    finally:
        os.unlink(temp_file)

def test_advanced_crewai():
    """Test advanced CrewAI features"""
    print("\nTesting advanced CrewAI features...")
    
    config = """
framework: "crewai"
topic: "Advanced AI Testing"
process: "sequential"
memory: true
verbose: false
planning: false
output_log_file: "test_crew.log"
max_rpm: 30

inputs:
  test_param: "test_value"

roles:
  advanced_tester:
    role: "Advanced Tester"
    goal: "Test advanced features"
    backstory: "Expert in testing complex systems"
    allow_delegation: false
    cache: true
    max_iter: 5
    verbose: true
    llm:
      model: "openai/gpt-4o"
    tasks:
      advanced_test:
        description: "Test advanced features with {test_param}"
        expected_output: "Advanced test results"
        output_file: "test_output.md"
        human_input: false
        async_execution: false
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config)
        temp_file = f.name
    
    try:
        praisonai = PraisonAI(agent_file=temp_file, framework="crewai")
        print("✅ Advanced CrewAI configuration loaded successfully")
    except Exception as e:
        print(f"❌ Advanced CrewAI test failed: {e}")
    finally:
        os.unlink(temp_file)
        # Clean up output files if created
        for file in ["test_crew.log", "test_output.md"]:
            if os.path.exists(file):
                os.unlink(file)

def test_hierarchical_process():
    """Test hierarchical process with manager"""
    print("\nTesting hierarchical process...")
    
    config = """
framework: "crewai"
topic: "Hierarchical Testing"
process: "hierarchical"
memory: true

manager_llm:
  model: "openai/gpt-4o"

roles:
  lead:
    role: "Team Lead"
    goal: "Coordinate testing"
    backstory: "Experienced team lead"
    allow_delegation: true
    tasks:
      coordinate:
        description: "Coordinate team testing efforts"
        expected_output: "Coordination plan"
  
  tester:
    role: "Tester"
    goal: "Execute tests"
    backstory: "Testing specialist"
    allow_delegation: false
    tasks:
      execute:
        description: "Execute test cases"
        expected_output: "Test execution results"
        context:
          - coordinate
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config)
        temp_file = f.name
    
    try:
        praisonai = PraisonAI(agent_file=temp_file, framework="crewai")
        print("✅ Hierarchical process configuration loaded successfully")
    except Exception as e:
        print(f"❌ Hierarchical process test failed: {e}")
    finally:
        os.unlink(temp_file)

def main():
    """Run all tests"""
    print("=" * 50)
    print("CrewAI Advanced Features Test Suite")
    print("=" * 50)
    
    # Check if CrewAI is available
    try:
        import crewai
        print("✅ CrewAI is installed")
    except ImportError:
        print("❌ CrewAI is not installed. Please install with: pip install 'praisonai[crewai]'")
        return
    
    # Run tests
    test_basic_crewai()
    test_advanced_crewai()
    test_hierarchical_process()
    
    print("\n" + "=" * 50)
    print("Test suite completed")
    print("=" * 50)

if __name__ == "__main__":
    main()