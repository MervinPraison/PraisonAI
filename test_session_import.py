#!/usr/bin/env python3
"""
Test script to verify session.py import works correctly (which imports Memory)
"""

import sys
import os

# Add the praisonai-agents source to Python path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

try:
    from praisonaiagents.session import Session
    print('SUCCESS: Session import works correctly')
    print('Session class found:', Session)
    
    # This was the failing import chain
    from praisonaiagents.agents.agents import Agent, Task, PraisonAIAgents
    print('SUCCESS: Agent, Task, PraisonAIAgents import works correctly')
    
except ImportError as e:
    print('ERROR:', e)
    import traceback
    traceback.print_exc()
except Exception as e:
    print('UNEXPECTED ERROR:', e)
    import traceback
    traceback.print_exc()