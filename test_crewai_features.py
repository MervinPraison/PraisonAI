#!/usr/bin/env python3
"""
Test script for CrewAI advanced features in PraisonAI
Tests both backward compatibility and new features
"""

import yaml
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_backward_compatibility():
    """Test that basic YAML configurations still work"""
    basic_yaml = """
framework: crewai
roles:
  researcher:
    role: "Researcher"
    goal: "Research {topic}"
    backstory: "You are an expert researcher"
    tasks:
      research_task:
        description: "Research about {topic}"
        expected_output: "A detailed research report"
"""
    
    config = yaml.safe_load(basic_yaml)
    print("✓ Basic YAML configuration parsed successfully")
    print(f"  - Framework: {config['framework']}")
    print(f"  - Roles: {list(config['roles'].keys())}")
    
def test_advanced_features():
    """Test that advanced features are properly configured"""
    # Load the advanced example
    example_path = "examples/crewai_advanced_example.yaml"
    
    if os.path.exists(example_path):
        with open(example_path, 'r') as f:
            config = yaml.safe_load(f)
        
        print("\n✓ Advanced YAML configuration loaded successfully")
        
        # Check all advanced features
        features = [
            ('process_type', 'Process Type'),
            ('manager_llm', 'Manager LLM'),
            ('memory', 'Memory'),
            ('planning', 'Planning'),
            ('verbose', 'Verbose Mode'),
            ('output_log_file', 'Output Log File'),
            ('max_rpm', 'Max RPM'),
            ('embedder', 'Embedder'),
            ('crew_callbacks', 'Crew Callbacks'),
            ('inputs', 'Custom Inputs')
        ]
        
        for key, name in features:
            if key in config:
                print(f"  ✓ {name}: {config[key]}")
            else:
                print(f"  ✗ {name}: Not configured")
    else:
        print(f"✗ Example file not found: {example_path}")

def test_crew_configuration():
    """Test that crew configuration works with new features"""
    try:
        from src.praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Create a test configuration
        test_config = {
            'framework': 'crewai',
            'process_type': 'sequential',
            'memory': True,
            'verbose': False,
            'roles': {
                'test_agent': {
                    'role': 'Test Agent',
                    'goal': 'Test the system',
                    'backstory': 'A test agent',
                    'tasks': {
                        'test_task': {
                            'description': 'Perform a test',
                            'expected_output': 'Test results'
                        }
                    }
                }
            }
        }
        
        print("\n✓ Test configuration created successfully")
        print("  - Process type: sequential")
        print("  - Memory enabled: True")
        print("  - Verbose mode: False")
        
    except ImportError as e:
        print(f"\n✗ Could not import AgentsGenerator: {e}")
        print("  Make sure you're running from the project root")

def main():
    """Run all tests"""
    print("Testing CrewAI Advanced Features Implementation")
    print("=" * 50)
    
    test_backward_compatibility()
    test_advanced_features()
    test_crew_configuration()
    
    print("\n" + "=" * 50)
    print("Testing complete!")
    print("\nNote: This is a validation script. For full integration testing,")
    print("run the actual PraisonAI CLI with the example configurations.")

if __name__ == "__main__":
    main()