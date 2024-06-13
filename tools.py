# tools.py
from duckduckgo_search import DDGS
from praisonai_tools import BaseTool

class InternetSearchTool(BaseTool):
    name: str = "InternetSearchTool"
    description: str = "Search Internet for relevant information based on a query or latest news"

    def _run(self, query: str):
        ddgs = DDGS()
        results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
        return results

from interpreter import interpreter
from praisonai_tools import BaseTool

class OpenInterpreterTool(BaseTool):
    name: str = "Open Interpreter Tool"
    description: str = "Use Open Interpreter configured to create and execute code based on natural language commands."

    def __init__(self):
        super().__init__()
        interpreter.auto_run = True

    def _run(self, code: str):
        result = interpreter.chat(code)
        return result

# Example usage
if __name__ == "__main__":
    tool = OpenInterpreterTool()
    code = "Plot AAPL and META's normalized stock prices"
    output = tool._run(code)
    print(output)