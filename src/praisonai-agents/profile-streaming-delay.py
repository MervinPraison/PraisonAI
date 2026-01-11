#!/usr/bin/env python3
"""
Detailed profiler to identify the exact source of streaming delay.
Traces every step from agent.start() to HTTP request.
"""

import os
import sys
import time
import functools

os.environ['LOGLEVEL'] = 'DEBUG'

# Microsecond precision timestamps
def ts():
    return time.perf_counter()

start_time = ts()

def log(msg):
    elapsed = (ts() - start_time) * 1000
    print(f"[{elapsed:8.2f}ms] {msg}")

log("Script starting...")

# ============================================================
# PATCH 1: OpenAI client initialization
# ============================================================
import openai

original_openai_init = openai.OpenAI.__init__

@functools.wraps(original_openai_init)
def traced_openai_init(self, *args, **kwargs):
    t0 = ts()
    result = original_openai_init(self, *args, **kwargs)
    log(f"OpenAI.__init__() took {(ts()-t0)*1000:.2f}ms")
    return result

openai.OpenAI.__init__ = traced_openai_init

# ============================================================
# PATCH 2: OpenAI completions.create
# ============================================================
original_create = openai.resources.chat.completions.Completions.create

@functools.wraps(original_create)
def traced_create(self, *args, **kwargs):
    log(f">>> OpenAI.create() CALLED - stream={kwargs.get('stream', False)}")
    t0 = ts()
    result = original_create(self, *args, **kwargs)
    log(f"<<< OpenAI.create() RETURNED in {(ts()-t0)*1000:.2f}ms")
    return result

openai.resources.chat.completions.Completions.create = traced_create

# ============================================================
# PATCH 3: httpx.Client.send (actual HTTP request)
# ============================================================
import httpx

original_send = httpx.Client.send

@functools.wraps(original_send)
def traced_send(self, request, *args, **kwargs):
    log(f">>> HTTPX.send() {request.method} {request.url}")
    t0 = ts()
    result = original_send(self, request, *args, **kwargs)
    log(f"<<< HTTPX.send() returned in {(ts()-t0)*1000:.2f}ms - status={result.status_code}")
    return result

httpx.Client.send = traced_send

# ============================================================
# PATCH 4: Rich Live display
# ============================================================
from rich.live import Live

original_live_init = Live.__init__
original_live_enter = Live.__enter__
original_live_exit = Live.__exit__

@functools.wraps(original_live_init)
def traced_live_init(self, *args, **kwargs):
    log(f">>> Live.__init__() called")
    t0 = ts()
    result = original_live_init(self, *args, **kwargs)
    log(f"<<< Live.__init__() took {(ts()-t0)*1000:.2f}ms")
    return result

@functools.wraps(original_live_enter)
def traced_live_enter(self):
    log(f">>> Live.__enter__() called")
    t0 = ts()
    result = original_live_enter(self)
    log(f"<<< Live.__enter__() took {(ts()-t0)*1000:.2f}ms")
    return result

@functools.wraps(original_live_exit)
def traced_live_exit(self, *args):
    log(f">>> Live.__exit__() called")
    t0 = ts()
    result = original_live_exit(self, *args)
    log(f"<<< Live.__exit__() took {(ts()-t0)*1000:.2f}ms")
    return result

Live.__init__ = traced_live_init
Live.__enter__ = traced_live_enter
Live.__exit__ = traced_live_exit

log("Patches applied, importing praisonaiagents...")

# ============================================================
# Import and trace Agent
# ============================================================
t0 = ts()
from praisonaiagents import Agent
log(f"Agent import took {(ts()-t0)*1000:.2f}ms")

# ============================================================
# PATCH 5: Agent methods
# ============================================================
from praisonaiagents.agent.agent import Agent as AgentClass

original_chat_completion = AgentClass._chat_completion
original_format_tools = AgentClass._format_tools_for_completion

@functools.wraps(original_chat_completion)
def traced_chat_completion(self, messages, temperature=1.0, tools=None, stream=True, 
                           reasoning_steps=False, task_name=None, task_description=None, task_id=None):
    log(f">>> Agent._chat_completion() stream={stream}, _using_custom_llm={self._using_custom_llm}")
    t0 = ts()
    result = original_chat_completion(self, messages, temperature, tools, stream, 
                                      reasoning_steps, task_name, task_description, task_id)
    log(f"<<< Agent._chat_completion() took {(ts()-t0)*1000:.2f}ms")
    return result

@functools.wraps(original_format_tools)
def traced_format_tools(self, tools):
    log(f">>> Agent._format_tools_for_completion() tools={tools}")
    t0 = ts()
    result = original_format_tools(self, tools)
    log(f"<<< Agent._format_tools_for_completion() took {(ts()-t0)*1000:.2f}ms")
    return result

AgentClass._chat_completion = traced_chat_completion
AgentClass._format_tools_for_completion = traced_format_tools

# ============================================================
# PATCH 6: OpenAIClient methods
# ============================================================
from praisonaiagents.llm.openai_client import OpenAIClient

original_chat_with_tools = OpenAIClient.chat_completion_with_tools
original_process_stream = OpenAIClient.process_stream_response
original_create_completion = OpenAIClient.create_completion
original_format_tools_client = OpenAIClient.format_tools

@functools.wraps(original_chat_with_tools)
def traced_chat_with_tools(self, *args, **kwargs):
    log(f">>> OpenAIClient.chat_completion_with_tools() stream={kwargs.get('stream', True)}")
    t0 = ts()
    result = original_chat_with_tools(self, *args, **kwargs)
    log(f"<<< OpenAIClient.chat_completion_with_tools() took {(ts()-t0)*1000:.2f}ms")
    return result

@functools.wraps(original_process_stream)
def traced_process_stream(self, *args, **kwargs):
    log(f">>> OpenAIClient.process_stream_response()")
    t0 = ts()
    result = original_process_stream(self, *args, **kwargs)
    log(f"<<< OpenAIClient.process_stream_response() took {(ts()-t0)*1000:.2f}ms")
    return result

@functools.wraps(original_create_completion)
def traced_create_completion(self, *args, **kwargs):
    log(f">>> OpenAIClient.create_completion() stream={kwargs.get('stream', False)}")
    t0 = ts()
    result = original_create_completion(self, *args, **kwargs)
    log(f"<<< OpenAIClient.create_completion() took {(ts()-t0)*1000:.2f}ms")
    return result

@functools.wraps(original_format_tools_client)
def traced_format_tools_client(self, tools):
    log(f">>> OpenAIClient.format_tools() tools count={len(tools) if tools else 0}")
    t0 = ts()
    result = original_format_tools_client(self, tools)
    log(f"<<< OpenAIClient.format_tools() took {(ts()-t0)*1000:.2f}ms")
    return result

OpenAIClient.chat_completion_with_tools = traced_chat_with_tools
OpenAIClient.process_stream_response = traced_process_stream
OpenAIClient.create_completion = traced_create_completion
OpenAIClient.format_tools = traced_format_tools_client

# ============================================================
# PATCH 7: sync_client property (lazy init)
# ============================================================
original_sync_client_getter = OpenAIClient.sync_client.fget

def traced_sync_client_getter(self):
    log(f">>> OpenAIClient.sync_client property accessed")
    t0 = ts()
    result = original_sync_client_getter(self)
    log(f"<<< OpenAIClient.sync_client took {(ts()-t0)*1000:.2f}ms")
    return result

OpenAIClient.sync_client = property(traced_sync_client_getter)

log("All patches applied. Creating agent...")

# ============================================================
# RUN THE TEST
# ============================================================
t0 = ts()
agent = Agent(
    instructions="You are a helpful assistant"
)
log(f"Agent created in {(ts()-t0)*1000:.2f}ms")
log(f"Agent.stream={agent.stream}, Agent.verbose={agent.verbose}")

log("=" * 60)
log("Starting agent.start()...")
log("=" * 60)

t0 = ts()
result = agent.start("Say hello in one word")
log(f"agent.start() completed in {(ts()-t0)*1000:.2f}ms")

log("=" * 60)
log("DONE")
log("=" * 60)
