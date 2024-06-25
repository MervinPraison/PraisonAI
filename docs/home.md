# Home

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