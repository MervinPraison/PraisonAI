# TL;DR

## Quick Start with CrewAI (Default)

```bash
# Install with CrewAI support
pip install "praisonai[crewai]"

# Set your API key
export OPENAI_API_KEY="Enter your API key"

# Initialize and run
praisonai --init "create a movie script about dog in moon"
praisonai
```

## Quick Start with AutoGen

```bash
# Install with AutoGen support
pip install "praisonai[autogen]"

# Set your API key
export OPENAI_API_KEY="Enter your API key"

# Initialize and run
praisonai --framework autogen --init "create a movie script about dog in moon"
praisonai --framework autogen
```

## User Interface

```bash
# Install UI support
pip install "praisonai[ui]"

# Set up environment
export OPENAI_API_KEY="Enter your API key"
chainlit create-secret
export CHAINLIT_AUTH_SECRET=xxxxxxxx

# Run UI
praisonai ui
```