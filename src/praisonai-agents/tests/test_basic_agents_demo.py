#!/usr/bin/env python3
"""
Demo script to showcase the enhanced basic-agents.py functionality
"""

import subprocess
import sys

def run_command(cmd):
    """Run a command and print the output"""
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print('='*60)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("Enhanced Basic Agents Demo")
    print("This script demonstrates the new features of basic-agents.py\n")
    
    # Show help
    print("\n1. Showing help information:")
    run_command([sys.executable, "tests/basic-agents.py", "--help"])
    
    # Single question mode
    print("\n2. Single question mode:")
    run_command([sys.executable, "tests/basic-agents.py", "What is Python programming?"])
    
    # Using different model
    print("\n3. Using a different model:")
    run_command([sys.executable, "tests/basic-agents.py", "--model", "gpt-4o-mini", "Explain quantum computing in simple terms"])
    
    # With debug logging
    print("\n4. With debug logging:")
    run_command([sys.executable, "tests/basic-agents.py", "--log-level", "DEBUG", "Why do leaves change color?"])
    
    print("\n5. Interactive mode:")
    print("To test interactive mode, run:")
    print("  python tests/basic-agents.py")
    print("  python tests/basic-agents.py --interactive")
    
    print("\n6. Check logs:")
    print("Log files are created in the 'logs' directory with timestamps")
    
if __name__ == "__main__":
    main()