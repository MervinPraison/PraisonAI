#!/usr/bin/env python3
"""
Langtrace Wrapper Script
Run any Python script with automatic Langtrace initialization
Usage: python run_with_langtrace.py <script_name.py>
"""
import sys
import os

# Initialize Langtrace before any other imports
from langtrace_python_sdk import langtrace

# Get API key from environment or use default
api_key = os.getenv('LANGTRACE_API_KEY', os.environ.get('LANGTRACE_API_KEY'))
api_host = os.getenv('LANGTRACE_API_HOST', 'http://localhost:3000/api/trace')

# Initialize Langtrace
langtrace.init(api_key=api_key, api_host=api_host)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_with_langtrace.py <script_name.py>")
        sys.exit(1)
    
    script_to_run = sys.argv[1]
    
    # Execute the target script
    with open(script_to_run, 'r') as f:
        script_content = f.read()
    
    # Execute in the same namespace
    exec(script_content, {'__name__': '__main__'})
