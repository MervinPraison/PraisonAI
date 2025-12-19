# PraisonAI Examples

This folder contains examples for PraisonAI. For detailed documentation, visit [docs.praison.ai](https://docs.praison.ai).

## Structure

```
examples/
├── python/           # Python examples
│   ├── agents/       # Agent examples (single, multi, router, etc.)
│   ├── workflows/    # Workflow patterns (routing, parallel, loop)
│   ├── tools/        # Custom tools examples
│   ├── mcp/          # MCP protocol examples
│   ├── memory/       # Memory and sessions
│   ├── code/         # Code editing and external CLI tools
│   └── ...
├── yaml/             # YAML workflow examples
└── cookbooks/        # Complete use-case examples
```

## Quick Links

| Category | Examples | Docs |
|----------|----------|------|
| **Agents** | [python/agents/](python/agents/) | [📖](https://docs.praison.ai/concepts/agents) |
| **Workflows** | [python/workflows/](python/workflows/) | [📖](https://docs.praison.ai/features/workflows) |
| **Model Router** | [python/agents/router-agent-cost-optimization.py](python/agents/router-agent-cost-optimization.py) | [📖](https://docs.praison.ai/features/model-router) |
| **MCP** | [python/mcp/](python/mcp/) | [📖](https://docs.praison.ai/mcp) |
| **Memory** | [python/memory/](python/memory/) | [📖](https://docs.praison.ai/concepts/memory) |
| **Tools** | [python/tools/](python/tools/) | [📖](https://docs.praison.ai/tools) |
| **Code** | [python/code/](python/code/) | [📖](https://docs.praison.ai/code) |
| **YAML** | [yaml/](yaml/) | [📖](https://docs.praison.ai/features/yaml-workflows) |

## Running Examples

```bash
# Install PraisonAI
pip install praisonai

# Set API key
export OPENAI_API_KEY=your_key_here

# Run an example
python examples/python/agents/single-agent.py
```

## CLI Commands

See the main [README.md](../README.md#-cli--no-code-interface) for all CLI commands.
