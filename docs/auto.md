# Auto Generation Mode

PraisonAI supports automatic agent generation with both CrewAI and AutoGen frameworks.

## Installation

Choose your preferred framework:

```bash
# For CrewAI
pip install "praisonai[crewai]"

# For AutoGen
pip install "praisonai[autogen]"

# For both frameworks
pip install "praisonai[crewai,autogen]"
```

## Usage

### With CrewAI (Default)
```bash
praisonai --auto "create a movie script about Dog in Moon"
```

### With AutoGen
```bash
praisonai --framework autogen --auto "create a movie script about Dog in Moon"
```

## Framework-specific Features

### CrewAI
- Task delegation capabilities
- Sequential and parallel task execution
- Built-in tools integration
- Structured agent-task relationships

### AutoGen
- Multi-agent conversation capabilities
- Code execution environment
- Built-in tools integration
- Flexible agent interactions

```bash
praisonai --auto "create a movie script about Dog in Moon"
```