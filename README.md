<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo/dark.png" />
    <source media="(prefers-color-scheme: light)" srcset="docs/logo/light.png" />
    <img alt="PraisonAI Logo" src="docs/logo/light.png" />
  </picture>
</p>

<p align="center">
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://static.pepy.tech/badge/PraisonAI" alt="Total Downloads" /></a>
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://img.shields.io/github/v/release/MervinPraison/PraisonAI" alt="Latest Stable Version" /></a>
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License" /></a>
</p>

<div align="center">

# Praison AI

<a href="https://trendshift.io/repositories/9130" target="_blank"><img src="https://trendshift.io/api/badge/repositories/9130" alt="MervinPraison%2FPraisonAI | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

</div>

Praison AI, leveraging both AutoGen and CrewAI or any other agent framework, represents a low-code, centralised framework designed to simplify the creation and orchestration of multi-agent systems for various LLM applications, emphasizing ease of use, customization, and human-agent interaction.

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/architecture-dark.png" />
    <source media="(prefers-color-scheme: light)" srcset="docs/images/architecture-light.png" />
    <img alt="PraisonAI Architecture" src="docs/images/architecture-light.png" />
  </picture>
</div>

## Different User Interfaces:

| Interface | Description | URL |
|---|---|---|
| **UI** | Multi Agents such as CrewAI or AutoGen | [https://docs.praison.ai/ui/ui](https://docs.praison.ai/ui/ui) |
| **Chat** | Chat with 100+ LLMs, single AI Agent | [https://docs.praison.ai/ui/chat](https://docs.praison.ai/ui/chat) |
| **Code** | Chat with entire Codebase, single AI Agent | [https://docs.praison.ai/ui/code](https://docs.praison.ai/ui/code) |
| **Realtime** | Real-time voice interaction with AI | [https://docs.praison.ai/ui/realtime](https://docs.praison.ai/ui/realtime) |

| Other Features | Description | Docs |
|---|---|---|
| **Train** | Fine-tune LLMs using your custom data | [https://docs.praison.ai/train](https://docs.praison.ai/train) |


## Google Colab Multi Agents

|               | Cookbook        | Open in Colab                                                                                                                                                                                                                                  |
| ------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Basic         | PraisonAI       | <a target="_blank" href="https://colab.research.google.com/github/MervinPraison/PraisonAI/blob/main/cookbooks/praisonai-googlecolab.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab" /></a>       |
| Include Tools | PraisonAI Tools | <a target="_blank" href="https://colab.research.google.com/github/MervinPraison/PraisonAI/blob/main/cookbooks/praisonai-tools-googlecolab.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab" /></a> |

## Installation Options

### Basic Installation
```bash
pip install praisonai
```

### Framework-specific Installation
```bash
# Install with CrewAI support
pip install "praisonai[crewai]"

# Install with AutoGen support
pip install "praisonai[autogen]"

# Install with both frameworks
pip install "praisonai[crewai,autogen]"
```

### UI and Additional Features
```bash
# Install UI support
pip install "praisonai[ui]"

# Install Chat interface
pip install "praisonai[chat]"

# Install Code interface
pip install "praisonai[code]"

# Install Realtime voice interaction
pip install "praisonai[realtime]"

# Install Call feature
pip install "praisonai[call]"
```

## Quick Start

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="Enter your API key"

# Initialize with CrewAI (default)
praisonai --init "create a movie script about dog in moon"

# Or initialize with AutoGen
praisonai --framework autogen --init "create a movie script about dog in moon"

# Run the agents
praisonai
```

## Full Automatic Mode

```bash
# With CrewAI (default)
praisonai --auto "create a movie script about Dog in Moon"

# With AutoGen
praisonai --framework autogen --auto "create a movie script about Dog in Moon"
```

## Framework-specific Features

### CrewAI
When installing with `pip install "praisonai[crewai]"`, you get:
- CrewAI framework support
- PraisonAI tools integration
- Task delegation capabilities
- Sequential and parallel task execution

### AutoGen
When installing with `pip install "praisonai[autogen]"`, you get:
- AutoGen framework support
- PraisonAI tools integration
- Multi-agent conversation capabilities
- Code execution environment

## Key Features

- 🤖 Automated AI Agents Creation
- 🔄 Use CrewAI or AutoGen Framework
- 💯 100+ LLM Support
- 💻 Chat with ENTIRE Codebase
- 🖥️ Interactive UIs
- 📄 YAML-based Configuration
- 🛠️ Custom Tool Integration
- 🔍 Internet Search Capability (using Crawl4AI and Tavily)
- 👁️ Vision Language Model (VLM) Support
- 🎙️ Real-time Voice Interaction

## TL;DR Multi Agents

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

## Installation Multi Agents

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

### To initialise with a specific agent framework (Optional):

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

## PraisonAI User Interfaces:

| Interface | Description                                | URL                                                                   |
| --------- | ------------------------------------------ | --------------------------------------------------------------------- |
| **UI**    | Multi Agents such as CrewAI or AutoGen     | [https://docs.praisonai.com/ui/ui](https://docs.praison.ai/ui/ui)     |
| **Chat**  | Chat with 100+ LLMs, single AI Agent       | [https://docs.praisonai.com/ui/chat](https://docs.praison.ai/ui/chat) |
| **Code**  | Chat with entire Codebase, single AI Agent | [https://docs.praisonai.com/ui/code](https://docs.praison.ai/ui/code) |

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

- https://docs.praison.ai/chat/

```bash
pip install "praisonai[chat]"
export OPENAI_API_KEY="Enter your API key"
praisonai chat
```

### Internet Search

Praison AI Chat and Praison AI Code now includes internet search capabilities using Crawl4AI and Tavily, allowing you to retrieve up-to-date information during your conversations.

### Vision Language Model Support

You can now upload images and ask questions based on them using Vision Language Models. This feature enables visual understanding and analysis within your chat sessions.

## Praison AI Code

```bash
pip install "praisonai[code]"
export OPENAI_API_KEY="Enter your API key"
praisonai code
```

### Internet Search

Praison AI Code also includes internet search functionality, enabling you to find relevant code snippets and programming information online.

## Create Custom Tools

- https://docs.praison.ai/tools/custom/

## Agents Playbook

### Simple Playbook Example

```yaml
framework: crewai
topic: Artificial Intelligence
roles:
  screenwriter:
    backstory: "Skilled in crafting scripts with engaging dialogue about {topic}."
    goal: Create scripts from concepts.
    role: Screenwriter
    tasks:
      scriptwriting_task:
        description: "Develop scripts with compelling characters and dialogue about {topic}."
        expected_output: "Complete script ready for production."
```

## Use 100+ Models

- https://docs.praison.ai/models/

## Include praisonai package in your project

- https://docs.praison.ai/developers/wrapper
- https://docs.praison.ai/developers/wrapper-tools/

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

## License

Praison AI is an open-sourced software licensed under the **[MIT license](https://opensource.org/licenses/MIT)**.

## Video Tutorials

| Topic | Video |
|-------|--------|
| Introduction | [![Introduction](https://img.youtube.com/vi/Fn1lQjC0GO0/0.jpg)](https://www.youtube.com/watch?v=Fn1lQjC0GO0) |
| Tools Overview | [![Tools Overview](https://img.youtube.com/vi/XaQRgRpV7jo/0.jpg)](https://www.youtube.com/watch?v=XaQRgRpV7jo) |
| Custom Tools | [![Custom Tools](https://img.youtube.com/vi/JSU2Rndh06c/0.jpg)](https://www.youtube.com/watch?v=JSU2Rndh06c) |
| Firecrawl Integration | [![Firecrawl](https://img.youtube.com/vi/UoqUDcLcOYo/0.jpg)](https://www.youtube.com/watch?v=UoqUDcLcOYo) |
| User Interface | [![UI](https://img.youtube.com/vi/tg-ZjNl3OCg/0.jpg)](https://www.youtube.com/watch?v=tg-ZjNl3OCg) |
| Crawl4AI Integration | [![Crawl4AI](https://img.youtube.com/vi/KAvuVUh0XU8/0.jpg)](https://www.youtube.com/watch?v=KAvuVUh0XU8) |
| Chat Interface | [![Chat](https://img.youtube.com/vi/sw3uDqn2h1Y/0.jpg)](https://www.youtube.com/watch?v=sw3uDqn2h1Y) |
| Code Interface | [![Code](https://img.youtube.com/vi/_5jQayO-MQY/0.jpg)](https://www.youtube.com/watch?v=_5jQayO-MQY) |
| Mem0 Integration | [![Mem0](https://img.youtube.com/vi/KIGSgRxf1cY/0.jpg)](https://www.youtube.com/watch?v=KIGSgRxf1cY) |
| Training | [![Training](https://img.youtube.com/vi/aLawE8kwCrI/0.jpg)](https://www.youtube.com/watch?v=aLawE8kwCrI) |
| Realtime Voice Interface | [![Realtime](https://img.youtube.com/vi/frRHfevTCSw/0.jpg)](https://www.youtube.com/watch?v=frRHfevTCSw) |
| Call Interface | [![Call](https://img.youtube.com/vi/m1cwrUG2iAk/0.jpg)](https://www.youtube.com/watch?v=m1cwrUG2iAk) |

## License

Praison AI is an open-sourced software licensed under the **[MIT license](https://opensource.org/licenses/MIT)**.

