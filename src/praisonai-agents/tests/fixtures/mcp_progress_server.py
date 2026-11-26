"""Small MCP stdio server used to test notifications/progress end to end."""

import asyncio

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ListToolsRequest, TextContent, Tool

server = Server("progress-test")
release_task = asyncio.Event()


@server.list_tools()
async def list_tools(_request: ListToolsRequest):
    return [
        Tool(
            name="long_task",
            description="Run a long task and report progress.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "hold": {"type": "boolean"},
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="release_task",
            description="Release the held test task.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None):
    if name == "release_task":
        release_task.set()
        return [types.TextContent(type="text", text="Released.")]
    if name != "long_task":
        raise ValueError(name)
    context = server.request_context
    token = context.meta.progressToken
    await context.session.send_progress_notification(token, 1, 2, "Started")
    if arguments.get("hold"):
        await release_task.wait()
    await asyncio.sleep(0.12)
    await context.session.send_progress_notification(token, 2, 2, "Almost done")
    return [TextContent(type="text", text=f"Completed {arguments['task']}.")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
