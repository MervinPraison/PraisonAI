# Create Custom Tools
## TL;DR to Create a Custom Tool

```bash
pip install praisonai duckduckgo-search
export OPENAI_API_KEY="Enter your API key"
praisonai --init research about the latest AI News and prepare a detailed report
```

- Add `- InternetSearchTool` in the agents.yaml file in the tools section. 
- Create a file called tools.py and add this code [tools.py](./tools.py)

```bash
praisonai
```

## Pre-requisite to Create a Custom Tool
`agents.yaml` file should be present in the current directory. 

If it doesn't exist, create it by running the command `praisonai --init research about the latest AI News and prepare a detailed report`.

### Step 1 to Create a Custom Tool

Create a file called tools.py in the same directory as the agents.yaml file.

```python
# example tools.py
from duckduckgo_search import DDGS
from praisonai_tools import BaseTool

class InternetSearchTool(BaseTool):
    name: str = "InternetSearchTool"
    description: str = "Search Internet for relevant information based on a query or latest news"

    def _run(self, query: str):
        ddgs = DDGS()
        results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
        return results
```

### Step 2 to Create a Custom Tool

Add the tool to the agents.yaml file as show below under the tools section `- InternetSearchTool`.

```yaml
framework: crewai
topic: research about the latest AI News and prepare a detailed report
roles:
  research_analyst:
    backstory: Experienced in gathering and analyzing data related to AI news trends.
    goal: Analyze AI News trends
    role: Research Analyst
    tasks:
      gather_data:
        description: Conduct in-depth research on the latest AI News trends from reputable
          sources.
        expected_output: Comprehensive report on current AI News trends.
    tools:
    - InternetSearchTool
```
