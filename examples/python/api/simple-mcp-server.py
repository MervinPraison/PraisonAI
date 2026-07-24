import socket
import sys
import threading
import time

from praisonaiagents import Agent


def _wait_until_ready(host: str, port: int, timeout: float = 15.0) -> bool:
    """Poll the MCP server port until it accepts connections or times out."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


if __name__ == "__main__":
    host, port = "127.0.0.1", 8080
    agent = Agent(name="TweetAgent", instructions="Create a Tweet based on the topic provided")
    server = threading.Thread(
        target=lambda: agent.launch(port=port, protocol="mcp", path="/mcp"),
        daemon=True,
    )
    server.start()

    if _wait_until_ready(host, port):
        print(f"MCP server started on http://{host}:{port}/mcp")
    else:
        print(f"MCP server failed to start on http://{host}:{port}/mcp", file=sys.stderr)
        sys.exit(1)
