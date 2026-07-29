import threading
import time

from praisonaiagents import Agent


if __name__ == "__main__":
    agent = Agent(name="TweetAgent", instructions="Create a Tweet based on the topic provided")
    server = threading.Thread(
        target=lambda: agent.launch(port=8080, protocol="mcp", path="/mcp"),
        daemon=True,
    )
    server.start()
    time.sleep(2)
    print("MCP server started on http://127.0.0.1:8080/mcp")