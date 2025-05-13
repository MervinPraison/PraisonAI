# MCP SSE Server and Client Implementation

This project demonstrates a working pattern for SSE-based MCP (Model Context Protocol) servers and clients. It consists of three main components:

1. **server.py**: An SSE-based MCP server that provides simple tools
2. **client.py**: A standalone client that connects to the server and uses its tools with Claude
3. **mcp-sse.py**: A client using praisonaiagents that connects to the server and uses its tools with OpenAI

## Tools Provided by the Server

The server implements two simple tools:

- **get_greeting**: Returns a personalized greeting for a given name
- **get_weather**: Returns simulated weather data for a given city

## Setup and Usage

### Prerequisites

Make sure you have the required packages installed:

```bash
pip install praisonaiagents mcp httpx starlette uvicorn anthropic python-dotenv
```

### Running the Server

First, start the MCP SSE server:

```bash
python server.py
```

By default, the server runs on 0.0.0.0:8080, but you can customize the host and port:

```bash
python server.py --host 127.0.0.1 --port 8081
```

### Running the Standalone Client

The standalone client uses Claude to interact with the MCP server tools:

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY=your_api_key_here

# Run the client
python client.py http://0.0.0.0:8080/sse
```

You'll see a prompt where you can type queries for Claude to process using the MCP tools.

### Running the praisonaiagents Client

The praisonaiagents client uses OpenAI to interact with the MCP server tools:

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=your_api_key_here

# Run the client
python mcp-sse.py
```

This will automatically send a query about the weather in Paris to the agent.

## How It Works

1. The server exposes MCP tools via an SSE endpoint
2. Clients connect to this endpoint and discover available tools
3. When a user makes a query, the client:
   - For client.py: Uses Claude to determine which tool to call
   - For mcp-sse.py: Uses OpenAI to determine which tool to call
4. The client executes the tool call against the server
5. The result is returned to the user

This pattern allows for decoupled processes where the MCP server can run independently of clients, making it suitable for cloud-native applications.

## Customizing

- To add more tools to the server, define new functions with the `@mcp.tool()` decorator in `server.py`
- To change the client's behavior, update the instructions and query in `mcp-sse.py` 