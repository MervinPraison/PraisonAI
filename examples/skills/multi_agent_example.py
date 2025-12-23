#!/usr/bin/env python3
"""
Example: Multi-Agent CLI Usage

This example demonstrates how to use the praisonai agents command
to define and run multiple agents from the command line.
"""

import subprocess
import os


def example_single_agent():
    """Run a single agent with a simple task."""
    print("=" * 60)
    print("Example 1: Single Agent")
    print("=" * 60)
    
    result = subprocess.run([
        "praisonai", "agents", "run",
        "--agent", "assistant:Helper",
        "--task", "What is the capital of France?"
    ], capture_output=True, text=True)
    
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")


def example_agent_with_tools():
    """Run an agent with tools."""
    print("\n" + "=" * 60)
    print("Example 2: Agent with Tools")
    print("=" * 60)
    
    result = subprocess.run([
        "praisonai", "agents", "run",
        "--agent", "researcher:Research Analyst:internet_search",
        "--task", "Find the latest news about renewable energy"
    ], capture_output=True, text=True)
    
    print(result.stdout)


def example_multiple_agents_sequential():
    """Run multiple agents in sequential mode."""
    print("\n" + "=" * 60)
    print("Example 3: Multiple Agents (Sequential)")
    print("=" * 60)
    
    result = subprocess.run([
        "praisonai", "agents", "run",
        "--agent", "researcher:Research Analyst:internet_search",
        "--agent", "writer:Content Writer:write_file",
        "--task", "Research AI trends and write a brief summary"
    ], capture_output=True, text=True)
    
    print(result.stdout)


def example_multiple_agents_parallel():
    """Run multiple agents in parallel mode."""
    print("\n" + "=" * 60)
    print("Example 4: Multiple Agents (Parallel)")
    print("=" * 60)
    
    result = subprocess.run([
        "praisonai", "agents", "run",
        "--agent", "analyst1:Market Analyst",
        "--agent", "analyst2:Tech Analyst",
        "--process", "parallel",
        "--task", "Analyze the current state of AI industry"
    ], capture_output=True, text=True)
    
    print(result.stdout)


def example_with_custom_llm():
    """Run agents with a custom LLM model."""
    print("\n" + "=" * 60)
    print("Example 5: Custom LLM Model")
    print("=" * 60)
    
    result = subprocess.run([
        "praisonai", "agents", "run",
        "--agent", "coder:Developer:execute_command",
        "--llm", "gpt-4o-mini",
        "--task", "Write a simple hello world Python script"
    ], capture_output=True, text=True)
    
    print(result.stdout)


def example_with_instructions():
    """Run agents with additional instructions."""
    print("\n" + "=" * 60)
    print("Example 6: With Additional Instructions")
    print("=" * 60)
    
    result = subprocess.run([
        "praisonai", "agents", "run",
        "--agent", "analyst:Data Analyst",
        "--instructions", "Be concise and provide only key insights",
        "--task", "Explain the benefits of using AI in healthcare"
    ], capture_output=True, text=True)
    
    print(result.stdout)


def example_list_tools():
    """List available tools for agents."""
    print("\n" + "=" * 60)
    print("Example 7: List Available Tools")
    print("=" * 60)
    
    result = subprocess.run([
        "praisonai", "agents", "list"
    ], capture_output=True, text=True)
    
    print(result.stdout)


if __name__ == "__main__":
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Some examples may fail.")
        print()
    
    # Run examples
    example_list_tools()
    example_single_agent()
    # Uncomment to run more examples:
    # example_agent_with_tools()
    # example_multiple_agents_sequential()
    # example_multiple_agents_parallel()
    # example_with_custom_llm()
    # example_with_instructions()
