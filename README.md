<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/praisonai-logo-large.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/images/praisonai-logo-black-large.png">
    <img alt="PraisonAI Logo" src="docs/images/praisonai-logo-black-large.png">
  </picture>
</p>
<div align="center">

# Praison AI

</div>

Praison AI, leveraging both AutoGen and CrewAI or any other agent framework, represents a low-code, centralised framework designed to simplify the creation and orchestration of multi-agent systems for various LLM applications, emphasizing ease of use, customization, and human-agent interaction.

## TL;DR
```bash
pip install praisonai
export OPENAI_API_KEY="Enter your API key"
praisonai --init create a movie script about dog in moon
praisonai
```

## Installation

```bash
pip install praisonai
```

## Initialise

```bash
export OPENAI_API_KEY="Enter your API key"
```

Generate your OPENAI API KEY from here: https://platform.openai.com/api-keys

Note: You can use other providers such as Ollama, Mistral ... etc. Details are provided at the bottom.
    
```bash
praisonai --init create a movie script about dog in moon
```
This will automatically create agents.yaml file in the current directory.

### To initialse with a specific agent framework (Optional):

```bash
praisonai --framework autogen --init create movie script about cat in mars
```

## Run

```bash
praisonai
```

or 
    
```bash
python -m praisonai
```

### Specify the agent framework (Optional):

```bash
praisonai --framework autogen
```

### Full Automatic Mode

```bash
praisonai --auto create a movie script about Dog in Moon
```

## User Interface

```bash
pip install -U "praisonai[ui]"
export OPENAI_API_KEY="Enter your API key"
chainlit create-secret
export CHAINLIT_AUTH_SECRET=xxxxxxxx
praisonai ui
```

or 

```
python -m praisonai ui
```

## Create Custom Tools

### TL;DR to Create a Custom Tool

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

### Pre-requisite to Create a Custom Tool
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

## Agents Playbook 

### Simple Playbook Example

```yaml
framework: crewai
topic: Artificial Intelligence
roles:
  screenwriter:
    backstory: 'Skilled in crafting scripts with engaging dialogue about {topic}.'
    goal: Create scripts from concepts.
    role: Screenwriter
    tasks:
      scriptwriting_task:
        description: 'Develop scripts with compelling characters and dialogue about {topic}.'
        expected_output: 'Complete script ready for production.'
```

## Include praisonai package in your project

```python
from praisonai import PraisonAI

def basic(): # Basic Mode
    praison_ai = PraisonAI(agent_file="agents.yaml")
    praison_ai.main()
    
def advanced(): # Advanced Mode with options
    praison_ai = PraisonAI(
        agent_file="agents.yaml",
        framework="autogen",
    )
    praison_ai.main()
    
def auto(): # Full Automatic Mode
    praison_ai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praison_ai.framework)
    praison_ai.main()

if __name__ == "__main__":
    basic()
    advanced()
    auto()
```

### Commands to Install Dependencies:

1. **Install all dependencies, including dev dependencies:**
   ```sh
   poetry install
   ```

2. **Install only documentation dependencies:**
   ```sh
   poetry install --with docs
   ```

3. **Install only test dependencies:**
   ```sh
   poetry install --with test
   ```

4. **Install only dev dependencies:**
   ```sh
   poetry install --with dev
   ```

This configuration ensures that your development dependencies are correctly categorized and installed as needed.

## Other Models

```bash
# Ollama
OPENAI_API_BASE='http://localhost:11434/v1'
OPENAI_MODEL_NAME='mistral'
OPENAI_API_KEY='NA'

# FastChat
OPENAI_API_BASE="http://localhost:8001/v1"
OPENAI_MODEL_NAME='oh-2.5m7b-q51'
OPENAI_API_KEY=NA

# LM Studio
OPENAI_API_BASE="http://localhost:1234/v1"
OPENAI_MODEL_NAME=NA
OPENAI_API_KEY=NA

# Mistral API
OPENAI_API_BASE=https://api.mistral.ai/v1
OPENAI_MODEL_NAME="mistral-small"
OPENAI_API_KEY=your-mistral-api-key
```

## Contributing

- Fork on GitHub: Use the "Fork" button on the repository page.
- Clone your fork: `git clone https://github.com/yourusername/praisonAI.git`
- Create a branch: `git checkout -b new-feature`
- Make changes and commit: `git commit -am "Add some feature"`
- Push to your fork: `git push origin new-feature`
- Submit a pull request via GitHub's web interface.
- Await feedback from project maintainers.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=MervinPraison/PraisonAI&type=Date)](https://docs.praison.ai)