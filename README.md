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

PraisonAI is a production-ready Multi-AI Agents framework with self-reflection, designed to create AI Agents to automate and solve problems ranging from simple tasks to complex challenges. By integrating PraisonAI Agents, AutoGen, and CrewAI into a low-code solution, it streamlines the building and management of multi-agent LLM systems, emphasising simplicity, customisation, and effective human-agent collaboration.

<div align="center">
  <a href="https://docs.praison.ai">
    <p align="center">
      <img src="https://img.shields.io/badge/📚_Documentation-Visit_docs.praison.ai-blue?style=for-the-badge&logo=bookstack&logoColor=white" alt="Documentation" />
    </p>
  </a>
</div>

## Key Features

- 🤖 Automated AI Agents Creation
- 🔄 Self Reflection AI Agents
- 🧠 Reasoning AI Agents
- 👁️ Multi Modal AI Agents
- 🤝 Multi Agent Collaboration
- 🎭 AI Agent Workflow
- 📚 Add Custom Knowledge
- 🧠 Agents with Short and Long Term Memory
- 📄 Chat with PDF Agents
- 💻 Code Interpreter Agents
- 📚 RAG Agents
- 🤔 Async & Parallel Processing
- 🔄 Auto Agents
- 🔢 Math Agents
- 🎯 Structured Output Agents
- 🔗 LangChain Integrated Agents
- 📞 Callback Agents
- 🤏 Mini AI Agents
- 🛠️ 100+ Custom Tools
- 📄 YAML Configuration
- 💯 100+ LLM Support

## Using Code

Light weight package dedicated for coding:
```bash
pip install praisonaiagents
```

```bash
export OPENAI_API_KEY=xxxxxxxxxxxxxxxxxxxxxx
```

### 1. Single Agent

Create app.py file and add the code below:
```python
from praisonaiagents import Agent
agent = Agent(instructions="Your are a helpful AI assistant")
agent.chat("Write a movie script about a robot in Mars")
```

Run:
```bash
python app.py
```

### 2. Multi Agents

Create app.py file and add the code below:
```python
from praisonaiagents import Agent, PraisonAIAgents

research_agent = Agent(instructions="Research about AI")
summarise_agent = Agent(instructions="Summarise research agent's findings")
agents = PraisonAIAgents(agents=[research_agent, summarise_agent])
agents.start()
```

Run:
```bash
python app.py
```

## Using No Code

### Auto Mode:
```bash
pip install praisonai
export OPENAI_API_KEY=xxxxxxxxxxxxxxxxxxxxxx
praisonai --auto create a movie script about Robots in Mars
```

## Adding Models

<div align="center">
  <a href="https://docs.praison.ai/models">
    <p align="center">
      <img src="https://img.shields.io/badge/%F0%9F%93%9A_Models-Visit_docs.praison.ai-blue?style=for-the-badge&logo=bookstack&logoColor=white" alt="Models" />
    </p>
  </a>
</div>

## Ollama Integration
```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
```

## Groq Integration
Replace xxxx with Groq API KEY:
```bash
export OPENAI_API_KEY=xxxxxxxxxxx
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

## No Code Options

## Agents Playbook

### Simple Playbook Example

```yaml
framework: praisonai
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
<div align="center">
  <a href="https://docs.praison.ai">
    <p align="center">
      <img src="https://img.shields.io/badge/📚_Documentation-Visit_docs.praison.ai-blue?style=for-the-badge&logo=bookstack&logoColor=white" alt="Documentation" />
    </p>
  </a>
</div>

## Development:

Below is used for development only.

### Using uv
```bash
# Install uv if you haven't already
pip install uv

# Install from requirements
uv pip install -r pyproject.toml

# Install with extras
uv pip install -r pyproject.toml --extra code
uv pip install -r pyproject.toml --extra "crewai,autogen"
```

## Contributing

- Fork on GitHub: Use the "Fork" button on the repository page.
- Clone your fork: `git clone https://github.com/yourusername/praisonAI.git`
- Create a branch: `git checkout -b new-feature`
- Make changes and commit: `git commit -am "Add some feature"`
- Push to your fork: `git push origin new-feature`
- Submit a pull request via GitHub's web interface.
- Await feedback from project maintainers.

## Other Features

- 🔄 Use CrewAI or AutoGen Framework
- 💻 Chat with ENTIRE Codebase
- 🎨 Interactive UIs
- 📄 YAML-based Configuration
- 🛠️ Custom Tool Integration
- 🔍 Internet Search Capability (using Crawl4AI and Tavily)
- 🖼️ Vision Language Model (VLM) Support
- 🎙️ Real-time Voice Interaction

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

