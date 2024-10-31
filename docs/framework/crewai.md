# CrewAI with PraisonAI

Low-code solution to run CrewAI with integrated tools and features.

## Installation

```bash
# Install with CrewAI support
pip install "praisonai[crewai]"
```

This installation includes:
- CrewAI framework
- PraisonAI tools integration
- Task delegation capabilities
- Sequential and parallel task execution

## Quick Start

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=xxxxxxxxxx

# Initialize with CrewAI
praisonai --framework crewai --init "Create a Movie Script About Cat in Mars"

# Run the agents
praisonai --framework crewai
```

## Auto Mode
```bash
praisonai --framework crewai --auto "Create a Movie Script About Cat in Mars"
```