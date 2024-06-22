# Praison AI

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

## Test
    
```bash
python -m unittest tests.test 
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

### Detailed Playbook Example

```yaml
framework: crewai
topic: Artificial Intelligence
roles:
  movie_concept_creator:
    backstory: 'Creative thinker with a deep understanding of cinematic storytelling,
      capable of using AI-generated storylines to create unique and compelling movie
      ideas.'
    goal: Generate engaging movie concepts using AI storylines
    role: Movie Concept Creator
    tasks:
      movie_concept_development:
        description: 'Develop movie concepts from AI-generated storylines, ensuring
          they are engaging and have strong narrative arcs.'
        expected_output: 'Well-structured movie concept document with character
          bios, settings, and plot outlines.'
  screenwriter:
    backstory: 'Expert in writing engaging dialogue and script structure, able to
      turn movie concepts into production-ready scripts.'
    goal: Write compelling scripts based on movie concepts
    role: Screenwriter
    tasks:
      scriptwriting_task:
        description: 'Turn movie concepts into polished scripts with well-developed
          characters, strong dialogue, and effective scene transitions.'
        expected_output: 'Production-ready script with a beginning, middle, and
          end, along with character development and engaging dialogues.'
  editor:
    backstory: 'Adept at identifying inconsistencies, improving language usage,
      and maintaining the overall flow of the script.'
    goal: Refine the scripts and ensure continuity of the movie storyline
    role: Editor
    tasks:
      editing_task:
        description: 'Review, edit, and refine the scripts to ensure they are cohesive
          and follow a well-structured narrative.'
        expected_output: 'A polished final draft of the script with no inconsistencies,
          strong character development, and effective dialogue.'
dependencies: []
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

## Include CrewAI Tools

```
pip install "praisonai[crewai-tools]"
```

## Deploy 
    
```bash
gcloud init
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com

export OPENAI_MODEL_NAME="gpt-4o"
export OPENAI_API_KEY="Enter your API key"
export OPENAI_API_BASE="https://api.openai.com/v1"

yes | gcloud auth configure-docker us-central1-docker.pkg.dev 
gcloud artifacts repositories create praisonai-repository --repository-format=docker --location=us-central1

PROJECT_ID=$(gcloud config get-value project)
TAG="latest"
docker build --platform linux/amd64 -t gcr.io/${PROJECT_ID}/praisonai-app:${TAG} .
docker tag gcr.io/${PROJECT_ID}/praisonai-app:${TAG} us-central1-docker.pkg.dev/${PROJECT_ID}/praisonai-repository/praisonai-app:${TAG}
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/praisonai-repository/praisonai-app:${TAG}

gcloud run deploy praisonai-service \
    --image us-central1-docker.pkg.dev/${PROJECT_ID}/praisonai-repository/praisonai-app:${TAG} \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars OPENAI_MODEL_NAME=${OPENAI_MODEL_NAME},OPENAI_API_KEY=${OPENAI_API_KEY},OPENAI_API_BASE=${OPENAI_API_BASE}
```

## Other Models

```bash
Ollama
OPENAI_API_BASE='http://localhost:11434/v1'
OPENAI_MODEL_NAME='mistral'
OPENAI_API_KEY='NA'

FastChat¶
OPENAI_API_BASE="http://localhost:8001/v1"
OPENAI_MODEL_NAME='oh-2.5m7b-q51'
OPENAI_API_KEY=NA

LM Studio¶
OPENAI_API_BASE="http://localhost:8000/v1"
OPENAI_MODEL_NAME=NA
OPENAI_API_KEY=NA

Mistral API¶
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

