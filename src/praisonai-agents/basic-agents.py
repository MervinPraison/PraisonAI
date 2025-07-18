from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)

# The start() method now automatically consumes the generator and displays the output
# Make sure to set OPENAI_API_KEY environment variable or pass api_key parameter
try:
    response = agent.start("Why sky is Blue?")
    print(f"Response: {response}")
except Exception as e:
    print(f"Error: {e}")
    print("Make sure to set OPENAI_API_KEY environment variable or pass api_key parameter to Agent()")
    print("Example: Agent(instructions='...', api_key='your-api-key')")