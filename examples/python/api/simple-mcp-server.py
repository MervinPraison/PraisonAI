from praisonaiagents import Agent

if __name__ == "__main__":
    agent = Agent(name="TweetAgent", instructions="Create a Tweet based on the topic provided")
    agent.launch(port=8080, protocol="mcp", path="/")