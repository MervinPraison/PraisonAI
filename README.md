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

|  | Cookbook | Open in Colab |
| --- | --- | --- |
| Basic | PraisonAI | <a target="_blank" href="https://colab.research.google.com/github/MervinPraison/PraisonAI/blob/main/cookbooks/praisonai-googlecolab.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a> |
| Include Tools | PraisonAI Tools | <a target="_blank" href="https://colab.research.google.com/github/MervinPraison/PraisonAI/blob/main/cookbooks/praisonai-tools-googlecolab.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a> |

## TL;DR
```bash
pip install praisonai
export OPENAI_API_KEY="Enter your API key"
praisonai --init create a movie script about dog in moon
praisonai
```

## Table of Contents

- [Installation](#installation)
- [Initialise](#initialise)
- [Run](#run)
- [Full Automatic Mode](#full-automatic-mode)
- [User Interface](#user-interface)
- [Praison AI Chat](#praison-ai-chat)
- [Create Custom Tools](#create-custom-tools)
- [Agents Playbook](#agents-playbook)
- [Include praisonai package in your project](#include-praisonai-package-in-your-project)
- [Commands to Install Dev Dependencies](#commands-to-install-dependencies)
- [Other Models](#other-models)
- [Contributing](#contributing)
- [Star History](#star-history)

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

## Praison AI Chat

* https://docs.praison.ai/chat/

```bash
pip install "praisonai[chat]"
export OPENAI_API_KEY="Enter your API key"
praisonai chat
```

## Create Custom Tools

* https://docs.praison.ai/tools/custom/

### Step 1: Pre-requisite to Create a Custom Tool
`agents.yaml` file should be present in the current directory. 

If it doesn't exist, create it by running the command `praisonai --init research about the latest AI News and prepare a detailed report`.

### Step 2: to Create a Custom Tool

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

### Step 3: to Create a Custom Tool

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

## Use 100+ Models

* https://docs.praison.ai/models/

## Include praisonai package in your project

* https://docs.praison.ai/developers/wrapper
* https://docs.praison.ai/developers/wrapper-tools/

## Option 1: Using RAW YAML

```python
from praisonai import PraisonAI

# Example agent_yaml content
agent_yaml = """
framework: "crewai"
topic: "Space Exploration"

roles:
  astronomer:
    role: "Space Researcher"
    goal: "Discover new insights about {topic}"
    backstory: "You are a curious and dedicated astronomer with a passion for unraveling the mysteries of the cosmos."
    tasks:
      investigate_exoplanets:
        description: "Research and compile information about exoplanets discovered in the last decade."
        expected_output: "A summarized report on exoplanet discoveries, including their size, potential habitability, and distance from Earth."
"""

# Create a PraisonAI instance with the agent_yaml content
praisonai = PraisonAI(agent_yaml=agent_yaml)

# Run PraisonAI
result = praisonai.run()

# Print the result
print(result)
```

## Option 2: Using separate agents.yaml file


Note: Please create agents.yaml file before hand. 

```python
from praisonai import PraisonAI

def basic(): # Basic Mode
    praisonai = PraisonAI(agent_file="agents.yaml")
    praisonai.run()

if __name__ == "__main__":
    basic()
```

## Commands to Install Dependencies:

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