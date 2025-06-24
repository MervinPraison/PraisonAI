#!/usr/bin/env python3
"""
AWS Bedrock Integration Example

This example demonstrates how to use various AWS Bedrock models with PraisonAI agents.

Requirements:
    pip install praisonaiagents boto3

Environment Variables:
    AWS_ACCESS_KEY_ID=your_access_key_id
    AWS_SECRET_ACCESS_KEY=your_secret_access_key
    AWS_REGION=us-east-1
"""

import os
from praisonaiagents import Agent

def main():
    """
    Example of using AWS Bedrock models with PraisonAI agents
    """
    
    # Verify AWS credentials are set
    required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION']
    for var in required_env_vars:
        if not os.getenv(var):
            print(f"Error: Environment variable {var} is not set")
            print("Please set your AWS credentials:")
            print("export AWS_ACCESS_KEY_ID=your_access_key_id")
            print("export AWS_SECRET_ACCESS_KEY=your_secret_access_key")
            print("export AWS_REGION=us-east-1")
            return
    
    print("AWS Bedrock Models Example")
    print("=" * 40)
    
    # Example 1: Anthropic Claude via Bedrock
    print("\n1. Using Anthropic Claude 3.5 Sonnet via Bedrock")
    claude_agent = Agent(
        instructions="You are a helpful assistant that provides concise, accurate responses.",
        llm={
            "model": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
            "temperature": 0.7
        }
    )
    
    response = claude_agent.ask("What is artificial intelligence in 50 words?")
    print(f"Claude Response: {response}")
    
    # Example 2: Amazon Titan via Bedrock
    print("\n2. Using Amazon Titan Text Express via Bedrock")
    titan_agent = Agent(
        instructions="You are a technical assistant focused on providing clear explanations.",
        llm={
            "model": "bedrock/amazon.titan-text-express-v1",
            "temperature": 0.5
        }
    )
    
    response = titan_agent.ask("Explain machine learning in simple terms.")
    print(f"Titan Response: {response}")
    
    # Example 3: Multi-agent conversation using different Bedrock models
    print("\n3. Multi-agent conversation with different Bedrock models")
    
    # Research agent using Claude
    researcher = Agent(
        instructions="You are a research specialist who gathers and analyzes information.",
        llm={
            "model": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
            "temperature": 0.3
        }
    )
    
    # Writer agent using Titan
    writer = Agent(
        instructions="You are a creative writer who crafts engaging content.",
        llm={
            "model": "bedrock/amazon.titan-text-express-v1",
            "temperature": 0.8
        }
    )
    
    # Research phase
    research_topic = "renewable energy trends"
    research_result = researcher.ask(f"Research the latest trends in {research_topic}. Provide 3 key insights.")
    print(f"Research Result: {research_result}")
    
    # Writing phase
    writing_result = writer.ask(f"Write a compelling introduction paragraph about renewable energy based on this research: {research_result}")
    print(f"Writing Result: {writing_result}")
    
    print("\n" + "=" * 40)
    print("AWS Bedrock integration demonstration complete!")

if __name__ == "__main__":
    main()