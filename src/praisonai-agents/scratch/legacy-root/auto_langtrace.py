"""
Auto Langtrace Module
Simply import this module to automatically initialize Langtrace tracing
Usage: from auto_langtrace import *
"""
import os
from langtrace_python_sdk import langtrace

# Auto-initialize Langtrace when this module is imported
api_key = os.getenv('LANGTRACE_API_KEY', os.environ.get('LANGTRACE_API_KEY'))
api_host = os.getenv('LANGTRACE_API_HOST', 'http://localhost:3000/api/trace')

# Initialize Langtrace automatically
langtrace.init(api_key=api_key, api_host=api_host)

print("✅ Langtrace automatically initialized")
