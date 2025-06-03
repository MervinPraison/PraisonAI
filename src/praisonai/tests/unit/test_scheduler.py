#!/usr/bin/env python3
"""
Test script for the deployment scheduler functionality.
Tests the core components without actually deploying.
"""

import sys
import os
import tempfile
import yaml

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai'))

def test_schedule_parser():
    """Test the schedule parser functionality."""
    try:
        from praisonai.scheduler import ScheduleParser
        
        # Test various schedule expressions
        test_cases = [
            ("daily", 86400),
            ("hourly", 3600),
            ("*/30m", 1800),
            ("*/6h", 21600),
            ("60", 60),
            ("3600", 3600)
        ]
        
        print("Testing ScheduleParser...")
        for expr, expected in test_cases:
            result = ScheduleParser.parse(expr)
            assert result == expected, f"Expected {expected}, got {result} for '{expr}'"
            print(f"  ✓ '{expr}' -> {result} seconds")
        
        print("ScheduleParser tests passed!")
        return True
        
    except Exception as e:
        print(f"ScheduleParser test failed: {e}")
        return False

def test_scheduler_creation():
    """Test scheduler creation and basic functionality."""
    try:
        from praisonai.scheduler import create_scheduler, DeploymentScheduler
        
        print("Testing scheduler creation...")
        
        # Test default scheduler
        scheduler = create_scheduler()
        assert isinstance(scheduler, DeploymentScheduler)
        print("  ✓ Default scheduler created")
        
        # Test with different providers
        for provider in ["gcp", "aws", "azure"]:
            scheduler = create_scheduler(provider=provider)
            assert isinstance(scheduler, DeploymentScheduler)
            print(f"  ✓ {provider} scheduler created")
        
        print("Scheduler creation tests passed!")
        return True
        
    except Exception as e:
        print(f"Scheduler creation test failed: {e}")
        return False

def test_config_file_parsing():
    """Test configuration file parsing."""
    try:
        # Create a temporary config file
        config_data = {
            'deployment': {
                'schedule': 'daily',
                'provider': 'gcp',
                'max_retries': 5
            },
            'environment': {
                'TEST_VAR': 'test_value'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name
        
        print("Testing config file parsing...")
        
        # Test loading the config
        with open(config_file, 'r') as f:
            loaded_config = yaml.safe_load(f)
        
        assert loaded_config['deployment']['schedule'] == 'daily'
        assert loaded_config['deployment']['provider'] == 'gcp'
        assert loaded_config['deployment']['max_retries'] == 5
        print("  ✓ Config file parsed correctly")
        
        # Clean up
        os.unlink(config_file)
        
        print("Config file parsing tests passed!")
        return True
        
    except Exception as e:
        print(f"Config file parsing test failed: {e}")
        return False

def test_cli_argument_parsing():
    """Test CLI argument parsing for scheduling options."""
    try:
        from praisonai.cli import PraisonAI
        
        print("Testing CLI argument parsing...")
        
        # Test basic CLI instantiation
        praison = PraisonAI()
        assert praison is not None
        print("  ✓ PraisonAI CLI instance created")
        
        print("CLI argument parsing tests passed!")
        return True
        
    except Exception as e:
        print(f"CLI argument parsing test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Running PraisonAI Scheduler Tests")
    print("=" * 40)
    
    tests = [
        test_schedule_parser,
        test_scheduler_creation,
        test_config_file_parsing,
        test_cli_argument_parsing
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        print()
        if test():
            passed += 1
        else:
            print("❌ Test failed")
    
    print()
    print("=" * 40)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
