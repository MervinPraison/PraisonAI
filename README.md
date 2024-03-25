# Praison AI

Praison AI, leveraging both AutoGen and CrewAI or any other agent framework, represents a low-code, centralised framework designed to simplify the creation and orchestration of multi-agent systems for various LLM applications, emphasizing ease of use, customization, and human-agent interaction.

## Installation

```bash
pip install praisonai
```

## Initialise
    
```bash
praisonai --init create a movie script about dog in moon
```
This will automatically create agents.yaml file in the current directory.


## Run

```bash
praisonai
```

or 
    
```bash
python -m praisonai
```

### Specify the agent framework

```bash
praisonai --framework autogen
```

### Full Automatic Mode

```bash
praisonai --auto create a movie script about Dog in Moon
```

## Test
    
```bash
python -m unittest tests.test 
```

## Agents Playbook 

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

## Deploy 
    
```bash
gcloud init
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com

export OPENAI_MODEL_NAME="gpt-4-turbo-preview"
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