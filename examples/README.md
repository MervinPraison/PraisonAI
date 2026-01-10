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
├── serve/            # Server and endpoints examples
├── yaml/             # YAML workflow examples
└── cookbooks/        # Complete use-case examples
```

## Quick Links

| Category | Examples | Docs |
|----------|----------|------|
| **Consolidated Params** | [consolidated_params/](consolidated_params/) | [📖](https://docs.praison.ai/api/consolidated-params) |
| **Agents** | [python/agents/](python/agents/) | [📖](https://docs.praison.ai/concepts/agents) |
| **Workflows** | [python/workflows/](python/workflows/) | [📖](https://docs.praison.ai/features/workflows) |
| **Model Router** | [python/agents/router-agent-cost-optimization.py](python/agents/router-agent-cost-optimization.py) | [📖](https://docs.praison.ai/features/model-router) |
| **MCP** | [python/mcp/](python/mcp/) | [📖](https://docs.praison.ai/mcp) |
| **Memory** | [python/memory/](python/memory/) | [📖](https://docs.praison.ai/concepts/memory) |
| **Tools** | [python/tools/](python/tools/) | [📖](https://docs.praison.ai/tools) |
| **Code** | [python/code/](python/code/) | [📖](https://docs.praison.ai/code) |
| **YAML** | [yaml/](yaml/) | [📖](https://docs.praison.ai/features/yaml-workflows) |
| **Doctor** | [doctor/](doctor/) | [📖](https://docs.praison.ai/cli/doctor) |
| **Serve** | [serve/](serve/) | [📖](https://docs.praison.ai/cli/serve) |
| **Endpoints** | [serve/](serve/) | [📖](https://docs.praison.ai/cli/endpoints) |

## Consolidated Params Examples

Agent-centric API with unified parameter resolution. Precedence: Instance > Config > Array > Dict > String > Bool > Default

| Example | Description |
|---------|-------------|
| [basic_agent.py](consolidated_params/basic_agent.py) | Minimal agent with memory |
| [basic_agents.py](consolidated_params/basic_agents.py) | Multi-agent with memory+planning |
| [basic_workflow.py](consolidated_params/basic_workflow.py) | Workflow with consolidated params |
| [basic_memory.py](consolidated_params/basic_memory.py) | Memory presets (file, redis, postgres) |
| [basic_guardrails.py](consolidated_params/basic_guardrails.py) | Guardrails with callable or config |
| [basic_workflow_agentlike.py](consolidated_params/basic_workflow_agentlike.py) | Workflow with agent-like params |
| [basic_step_override.py](consolidated_params/basic_step_override.py) | Step-level override of workflow defaults |
| [advanced_workflow_full_features.py](consolidated_params/advanced_workflow_full_features.py) | All consolidated params |

## Serve Examples

| Example | Description | CLI Command |
|---------|-------------|-------------|
| [unified_server.py](serve/unified_server.py) | All providers in one server | `praisonai serve unified` |
| [agent_as_api_single.py](serve/agent_as_api_single.py) | Single agent HTTP API | `praisonai serve agents` |
| [agents_as_api_router.py](serve/agents_as_api_router.py) | Multi-agent router API | `praisonai serve agents` |
| [a2a_server_client.py](serve/a2a_server_client.py) | A2A protocol server | `praisonai serve a2a` |
| [a2u_events_stream.py](serve/a2u_events_stream.py) | A2U event stream | `praisonai serve a2u` |
| [mcp_http_server.py](serve/mcp_http_server.py) | MCP HTTP server | `praisonai serve mcp` |
| [tools_as_mcp_server.py](serve/tools_as_mcp_server.py) | Tools as MCP server | `praisonai serve tools` |
| [agent_launch_modes.py](serve/agent_launch_modes.py) | Agent.launch() API | Python only |
| [endpoints_unified_client.py](serve/endpoints_unified_client.py) | Unified client | `praisonai endpoints` |

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
