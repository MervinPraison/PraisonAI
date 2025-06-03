import os
import asyncio
from pathlib import Path
import difflib
from typing import Dict, Any
from litellm import acompletion
import json
import dotenv
from tavily import TavilyClient
from crawl4ai import AsyncAsyncWebCrawler

dotenv.load_dotenv()

class AICoder:
    def __init__(self, cwd: str = None, tavily_api_key: str = None):
        self.cwd = cwd or os.getcwd()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "write_to_file",
                    "description": "Write content to a file at the specified path. If the file exists, it will be overwritten.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path of the file to write to."
                            },
                            "content": {
                                "type": "string",
                                "description": "The content to write to the file."
                            }
                        },
                        "required": ["path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Execute a CLI command on the system.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The CLI command to execute."
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file at the specified path.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path of the file to read."
                            }
                        },
                        "required": ["path"]
                    }
                }
            }
        ]

        self.tavily_api_key = tavily_api_key
        if self.tavily_api_key:
            self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
            self.tools.append({
                "type": "function",
                "function": {
                    "name": "tavily_web_search",
                    "description": "Search the web using Tavily API and crawl the resulting URLs",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            })
        else:
            self.tavily_client = None

    async def create_directories(self, file_path):
        file_path_obj = Path(file_path)
        dir_path = file_path_obj.parent
        if not dir_path.exists():
            os.makedirs(dir_path, exist_ok=True)
        return dir_path

    async def file_exists(self, file_path):
        return Path(file_path).exists()

    async def write_to_file(self, file_path, content, existing=False):
        if not existing:
            await self.create_directories(file_path)
        try:
            with open(file_path, 'w') as file:
                file.write(content)
            return True
        except Exception as e:
            return False

    async def read_file(self, file_path):
        try:
            with open(file_path, 'r') as file:
                return file.read()
        except:
            return None

    async def execute_command(self, command: str):
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd
            )
            stdout, stderr = await process.communicate()
            if stdout:
                return f"Command output:\n{stdout.decode()}"
            if stderr:
                return f"Command error:\n{stderr.decode()}"
            return process.returncode == 0
        except Exception as e:
            return f"Error executing command: {str(e)}"

    async def tavily_web_search(self, query):
        if not self.tavily_client:
            return json.dumps({
                "query": query,
                "error": "Tavily API key is not set. Web search is unavailable."
            })
        response = self.tavily_client.search(query)
        results = []
        async with AsyncAsyncWebCrawler() as crawler:
            for result in response.get('results', []):
                url = result.get('url')
                if url:
                    try:
                        crawl_result = await crawler.arun(url=url)
                        results.append({
                            "content": result.get('content'),
                            "url": url,
                            "full_content": crawl_result.markdown
                        })
                    except Exception:
                        results.append({
                            "content": result.get('content'),
                            "url": url,
                            "full_content": "Error: Unable to crawl this URL"
                        })
        return json.dumps({
            "query": query,
            "results": results
        })

    def generate_diff(self, original_content: str, new_content: str, filename="file.txt"):
        diff_lines = difflib.unified_diff(
            original_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"original_{filename}",
            tofile=f"modified_{filename}"
        )
        return "".join(diff_lines)

    def parse_json_response(self, json_object: Dict) -> Dict[str, Any]:
        if 'choices' in json_object and json_object['choices'][0]['message']:
            message = json_object['choices'][0]['message']
            if 'tool_calls' in message and message['tool_calls']:
                return {"type": "tool_calls", "data": message['tool_calls']}
            return {"type": "content", "data": message.get('content', "")}
        return {"type": "content", "data": json.dumps(json_object)}

    def parse_llm_response(self, response: Any) -> Dict[str, Any]:
        if response is None:
            return {"type": "content", "data": ""}
        if isinstance(response, str):
            try:
                json_object = json.loads(response)
                if isinstance(json_object, dict):
                    return self.parse_json_response(json_object)
            except json.JSONDecodeError:
                return {"type": "content", "data": response}
        if hasattr(response, 'choices') and response.choices:
            message = response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_calls_data = []
                for tool_call in message.tool_calls:
                    tool_calls_data.append({
                        'id': tool_call.id,
                        'type': tool_call.type,
                        'function': {
                            'name': tool_call.function.name,
                            'arguments': tool_call.function.arguments
                        }
                    })
                return {"type": "tool_calls", "data": tool_calls_data}
            return {"type": "content", "data": message.content or ""}
        return {"type": "content", "data": str(response)}

    async def apply_llm_response(self, task, llm_response):
        parsed_response = self.parse_llm_response(llm_response)
        if parsed_response["type"] == "tool_calls":
            for tool_call in parsed_response["data"]:
                if tool_call["function"]["name"] == "write_to_file":
                    args = json.loads(tool_call["function"]["arguments"])
                    file_path = os.path.join(self.cwd, args["path"].strip())
                    content = args["content"]
                    if await self.file_exists(file_path):
                        original_content = await self.read_file(file_path)
                        file_diff = self.generate_diff(original_content, content, os.path.basename(file_path))
                        # Interaction with user removed for automation context
                        return await self.write_to_file(file_path, content, True)
                    else:
                        return await self.write_to_file(file_path, content)
                elif tool_call["function"]["name"] == "execute_command":
                    args = json.loads(tool_call["function"]["arguments"])
                    command = args.get("command", "").strip()
                    if command:
                        return await self.execute_command(command)
                    else:
                        return False
                elif tool_call["function"]["name"] == "read_file":
                    args = json.loads(tool_call["function"]["arguments"])
                    file_path = args.get("path", "").strip()
                    if file_path:
                        content = await self.read_file(os.path.join(self.cwd, file_path))
                        return True if content is not None else False
                    else:
                        return False
                elif tool_call["function"]["name"] == "tavily_web_search":
                    args = json.loads(tool_call["function"]["arguments"])
                    return await self.tavily_web_search(args.get("query"))
                else:
                    return False
        return True

    async def process_task(self, task: str):
        llm_response = await acompletion(
            model="gpt-4",
            messages=[
                {"role": "user", "content": task}
            ],
            tools=self.tools,
            tool_choice="auto"
        )
        return await self.apply_llm_response(task, llm_response)

async def main():
    ai_coder = AICoder()
    await ai_coder.process_task("Create a file called `hello.txt` with the content 'Hello, world!'")
    await ai_coder.process_task("Edit the file called `hello.txt` and change the content to 'Hello again, world!'")
    await ai_coder.process_task("Show me the current working directory")
    await ai_coder.process_task("Read the contents of hello.txt")

if __name__ == "__main__":
    asyncio.run(main())