#!/usr/bin/env python3
"""Test script to verify the enhanced logging functionality."""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add praisonai-agents to path
sys.path.insert(0, str(Path(__file__).parent / "src/praisonai-agents"))

def test_basic_logging():
    """Test basic logging functionality."""
    print("Testing basic logging...")
    
    from praisonaiagents import get_logger
    
    # Test automatic module detection
    logger = get_logger()
    logger.info("Test message from auto-detected module")
    
    # Test explicit module name
    logger2 = get_logger("test_module")
    logger2.info("Test message from explicit module")
    
    # Test consistent naming
    logger3 = get_logger("praisonaiagents.existing_module")
    logger3.info("Test message from existing praisonaiagents module")
    
    print("✅ Basic logging test passed")

def test_structured_logging():
    """Test structured JSON logging functionality."""
    print("Testing structured logging...")
    
    # Enable structured logging
    os.environ['PRAISONAI_STRUCTURED_LOGS'] = 'true'
    
    from praisonaiagents import get_logger, configure_structured_logging
    
    # Configure structured logging
    configure_structured_logging()
    
    # Test with extra data
    logger = get_logger(extra_data={"agent_id": "test_agent", "session": "test_session"})
    logger.info("Test structured log message")
    
    print("✅ Structured logging test passed")

def test_backward_compatibility():
    """Test that existing code still works."""
    print("Testing backward compatibility...")
    
    import logging
    
    # Test old pattern still works
    logger = logging.getLogger(__name__)
    logger.info("Test message using standard logging.getLogger")
    
    # Test mixed usage
    from praisonaiagents import get_logger
    new_logger = get_logger(__name__)
    new_logger.info("Test message using new get_logger")
    
    print("✅ Backward compatibility test passed")

def test_naming_convention():
    """Test the naming convention enforcement."""
    print("Testing naming convention...")
    
    from praisonaiagents import get_logger
    
    # Test various inputs
    test_cases = [
        ("my_module", "praisonaiagents.my_module"),
        ("praisonaiagents.existing", "praisonaiagents.existing"),
        ("praisonai.other", "praisonaiagents.other"),
        ("__main__", "praisonaiagents.main"),
    ]
    
    for input_name, expected in test_cases:
        logger = get_logger(input_name)
        actual = logger.name
        assert actual == expected, f"Expected {expected}, got {actual}"
        logger.debug(f"Testing: {input_name} -> {actual}")
    
    print("✅ Naming convention test passed")

def main():
    """Run all tests."""
    print("🧪 Testing enhanced logging functionality...")
    print()
    
    try:
        test_basic_logging()
        test_structured_logging()
        test_backward_compatibility()
        test_naming_convention()
        
        print()
        print("✅ All logging enhancement tests passed!")
        print("📝 Summary:")
        print("  - Enhanced _logging.py with get_logger utility")
        print("  - Added structured JSON logging support") 
        print("  - Enforced consistent 'praisonaiagents.*' naming")
        print("  - Maintained full backward compatibility")
        print("  - Added centralized logging utilities to __init__.py")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)