#!/usr/bin/env python3
"""
Test script for sandbox implementation.

Tests the new sandbox manager and agent integration.
"""

import asyncio
import logging
import sys
import os

# Add the source directories to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "praisonai-agents"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "praisonai"))

from praisonaiagents.sandbox import (
    SandboxConfig, 
    SandboxManager, 
    check_code_safety,
    format_warnings
)
from praisonaiagents import Agent

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_sandbox_manager():
    """Test SandboxManager factory functionality."""
    print("🧪 Testing SandboxManager...")
    
    # Test subprocess sandbox (should always be available)
    config = SandboxConfig.subprocess()
    manager = SandboxManager(config)
    
    # Test available types
    available = manager.get_available_types()
    print(f"Available sandbox types: {list(available.keys())}")
    
    # Test code execution
    code = """
x = 40
y = 2
result = x + y
print(f"The answer is {result}")
"""
    
    try:
        result = await manager.run_code(code)
        print(f"✅ Sandbox execution successful!")
        print(f"   Status: {result.status}")
        print(f"   Exit code: {result.exit_code}")
        print(f"   Output: {result.stdout.strip()}")
        print(f"   Duration: {result.duration_seconds:.3f}s")
    except Exception as e:
        print(f"❌ Sandbox execution failed: {e}")


def test_security_checks():
    """Test security pre-checks functionality."""
    print("\n🔒 Testing Security Pre-checks...")
    
    # Safe code
    safe_code = "print('Hello, World!')"
    warnings = check_code_safety(safe_code)
    print(f"Safe code warnings: {len(warnings)}")
    
    # Dangerous code
    dangerous_code = """
import os
os.system('echo "dangerous"')
eval("print('dynamic code')")
"""
    warnings = check_code_safety(dangerous_code)
    print(f"Dangerous code warnings: {len(warnings)}")
    if warnings:
        formatted = format_warnings(warnings)
        print("Security warnings:")
        print(formatted)


def test_agent_integration():
    """Test Agent integration with sandbox."""
    print("\n🤖 Testing Agent Integration...")
    
    try:
        # Create agent with subprocess sandbox
        config = SandboxConfig.subprocess()
        agent = Agent(
            name="test_agent",
            sandbox=config,
        )
        
        print(f"✅ Agent created with sandbox")
        print(f"   Has sandbox: {agent.has_sandbox}")
        print(f"   Sandbox type: {agent.sandbox_config.sandbox_type}")
        
        # Test status
        status = agent.get_sandbox_status()
        print(f"   Status: {status}")
        
        # Test code execution (sync)
        code = "print('Hello from agent sandbox!')"
        result = agent.execute_code_sync(code)
        print(f"   Execution result: {result.stdout.strip()}")
        
    except Exception as e:
        print(f"❌ Agent integration failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main test runner."""
    print("🚀 Testing PraisonAI Sandbox Implementation\n")
    
    await test_sandbox_manager()
    test_security_checks()
    test_agent_integration()
    
    print("\n✨ Test complete!")


if __name__ == "__main__":
    asyncio.run(main())