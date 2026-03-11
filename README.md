<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo/dark.png" />
    <source media="(prefers-color-scheme: light)" srcset="docs/logo/light.png" />
    <img alt="PraisonAI Logo" src="docs/logo/light.png" />
  </picture>
</p>

<!-- mcp-name: io.github.MervinPraison/praisonai -->

<p align="center">
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://static.pepy.tech/badge/PraisonAI" alt="Total Downloads" /></a>
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://img.shields.io/github/v/release/MervinPraison/PraisonAI" alt="Latest Stable Version" /></a>
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License" /></a>
<a href="https://registry.modelcontextprotocol.io/servers/io.github.MervinPraison/praisonai"><img src="https://img.shields.io/badge/MCP-Registry-blue" alt="MCP Registry" /></a>
</p>

<div align="center">

# Praison AI

<a href="https://trendshift.io/repositories/9130" target="_blank"><img src="https://trendshift.io/api/badge/repositories/9130" alt="MervinPraison%2FPraisonAI | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

</div>

PraisonAI is a production-ready Multi-AI Agents framework with self-reflection, designed to create AI Agents to automate and solve problems ranging from simple tasks to complex challenges. It provides a low-code solution to streamline the building and management of multi-agent LLM systems, emphasising simplicity, customisation, and effective human-agent collaboration.

<div align="center">
  <a href="https://docs.praison.ai">
    <p align="center">
      <img src="https://img.shields.io/badge/📚_Documentation-Visit_docs.praison.ai-blue?style=for-the-badge&logo=bookstack&logoColor=white" alt="Documentation" />
    </p>
  </a>
</div>

---

> **Quick Paths:**
> - 🆕 **New here?** → [Quick Start](#-quick-start) *(1 minute to first agent)*
> - 📦 **Installing?** → [Installation](#-installation)
> - 🐍 **Python SDK?** → [Python Examples](#-using-python-code)
> - 🎯 **CLI user?** → [CLI Quick Reference](#cli-quick-reference)
> - 🤝 **Contributing?** → [Development](#-development)

---

## ⚡ Performance

PraisonAI Agents is the **fastest AI agent framework** for agent instantiation.

| Framework | Avg Time (μs) | Relative |
|-----------|---------------|----------|
| **PraisonAI** | **3.77** | **1.00x (fastest)** |
| OpenAI Agents SDK | 5.26 | 1.39x |
| Agno | 5.64 | 1.49x |
| PraisonAI (LiteLLM) | 7.56 | 2.00x |
| PydanticAI | 226.94 | 60.16x |
| LangGraph | 4,558.71 | 1,209x |

---

## 🚀 Quick Start

Get started with PraisonAI in under 1 minute:

```bash
# Install
pip install praisonaiagents

# Set API key
export OPENAI_API_KEY=your_key_here

# Create a simple agent
python -c "from praisonaiagents import Agent; Agent(instructions='You are a helpful AI assistant').start('Write a haiku about AI')"
```

> **Next Steps:** [Single Agent Example](#1-single-agent) | [Multi Agents](#2-multi-agents) | [Full Docs](https://docs.praison.ai)

---

## 📦 Installation

### Python SDK

Lightweight package dedicated for coding:

```bash
pip install praisonaiagents
```

For the full framework with CLI support:

```bash
pip install praisonai
```

### JavaScript SDK

```bash
npm install praisonai
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key |
| `ANTHROPIC_API_KEY` | No | Anthropic Claude API key |
| `GOOGLE_API_KEY` | No | Google Gemini API key |
| `GROQ_API_KEY` | No | Groq API key |
| `OPENAI_BASE_URL` | No | Custom API endpoint (for Ollama, Groq, etc.) |

> *At least one LLM provider API key is required.

```bash
# Set your API key
export OPENAI_API_KEY=your_key_here

# For Ollama (local models)
export OPENAI_BASE_URL=http://localhost:11434/v1

# For Groq
export OPENAI_API_KEY=your_groq_key
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

---

## ✨ Key Features

<details open>
<summary><strong>🤖 Core Agents</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Single Agent | [Example](examples/python/agents/single-agent.py) | [📖](https://docs.praison.ai/agents/single) |
| Multi Agents | [Example](examples/python/general/mini_agents_example.py) | [📖](https://docs.praison.ai/concepts/agents) |
| Auto Agents | [Example](examples/python/general/auto_agents_example.py) | [📖](https://docs.praison.ai/features/autoagents) |
| Self Reflection AI Agents | [Example](examples/python/concepts/self-reflection-details.py) | [📖](https://docs.praison.ai/features/selfreflection) |
| Reasoning AI Agents | [Example](examples/python/concepts/reasoning-extraction.py) | [📖](https://docs.praison.ai/features/reasoning) |
| Multi Modal AI Agents | [Example](examples/python/general/multimodal.py) | [📖](https://docs.praison.ai/features/multimodal) |

</details>

<details>
<summary><strong>🔄 Workflows</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Simple Workflow | [Example](examples/python/workflows/simple_workflow.py) | [📖](https://docs.praison.ai/features/workflows) |
| Workflow with Agents | [Example](examples/python/workflows/workflow_with_agents.py) | [📖](https://docs.praison.ai/features/workflows) |
| Agentic Routing (`route()`) | [Example](examples/python/workflows/workflow_routing.py) | [📖](https://docs.praison.ai/features/routing) |
| Parallel Execution (`parallel()`) | [Example](examples/python/workflows/workflow_parallel.py) | [📖](https://docs.praison.ai/features/parallelisation) |
| Loop over List/CSV (`loop()`) | [Example](examples/python/workflows/workflow_loop_csv.py) | [📖](https://docs.praison.ai/features/repetitive) |
| Evaluator-Optimizer (`repeat()`) | [Example](examples/python/workflows/workflow_repeat.py) | [📖](https://docs.praison.ai/features/evaluator-optimiser) |
| Conditional Steps | [Example](examples/python/workflows/workflow_conditional.py) | [📖](https://docs.praison.ai/features/workflows) |
| Workflow Branching | [Example](examples/python/workflows/workflow_branching.py) | [📖](https://docs.praison.ai/features/workflows) |
| Workflow Early Stop | [Example](examples/python/workflows/workflow_early_stop.py) | [📖](https://docs.praison.ai/features/workflows) |
| Workflow Checkpoints | [Example](examples/python/workflows/workflow_checkpoints.py) | [📖](https://docs.praison.ai/features/workflows) |

</details>

<details>
<summary><strong>💻 Code & Development</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Code Interpreter Agents | [Example](examples/python/agents/code-agent.py) | [📖](https://docs.praison.ai/features/codeagent) |
| AI Code Editing Tools | [Example](examples/python/code/code_editing_example.py) | [📖](https://docs.praison.ai/code/editing) |
| External Agents (All) | [Example](examples/python/code/external_agents_example.py) | [📖](https://docs.praison.ai/code/external-agents) |
| Claude Code CLI | [Example](examples/python/code/claude_code_example.py) | [📖](https://docs.praison.ai/code/claude-code) |
| Gemini CLI | [Example](examples/python/code/gemini_cli_example.py) | [📖](https://docs.praison.ai/code/gemini-cli) |
| Codex CLI | [Example](examples/python/code/codex_cli_example.py) | [📖](https://docs.praison.ai/code/codex-cli) |
| Cursor CLI | [Example](examples/python/code/cursor_cli_example.py) | [📖](https://docs.praison.ai/code/cursor-cli) |

</details>

<details>
<summary><strong>🧠 Memory & Knowledge</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Memory (Short & Long Term) | [Example](examples/python/general/memory_example.py) | [📖](https://docs.praison.ai/concepts/memory) |
| File-Based Memory | [Example](examples/python/general/memory_example.py) | [📖](https://docs.praison.ai/concepts/memory) |
| Claude Memory Tool | [Example](examples/python/memory/claude_memory_example.py) | [📖](https://docs.praison.ai/features/claude-memory-tool) |
| Add Custom Knowledge | [Example](examples/python/concepts/knowledge-agents.py) | [📖](https://docs.praison.ai/features/knowledge) |
| RAG Agents | [Example](examples/python/concepts/rag-agents.py) | [📖](https://docs.praison.ai/features/rag) |
| Chat with PDF Agents | [Example](examples/python/concepts/chat-with-pdf.py) | [📖](https://docs.praison.ai/features/chat-with-pdf) |
| Data Readers (PDF, DOCX, etc.) | [CLI](https://docs.praison.ai/cli/knowledge) | [📖](https://docs.praison.ai/api/praisonai/knowledge-readers-api) |
| Vector Store Selection | [CLI](https://docs.praison.ai/cli/knowledge) | [📖](https://docs.praison.ai/api/praisonai/knowledge-vector-store-api) |
| Retrieval Strategies | [CLI](https://docs.praison.ai/cli/knowledge) | [📖](https://docs.praison.ai/api/praisonai/knowledge-retrieval-api) |
| Rerankers | [CLI](https://docs.praison.ai/cli/knowledge) | [📖](https://docs.praison.ai/api/praisonai/knowledge-reranker-api) |
| Index Types (Vector/Keyword/Hybrid) | [CLI](https://docs.praison.ai/cli/knowledge) | [📖](https://docs.praison.ai/api/praisonai/knowledge-index-api) |
| Query Engines (Sub-Question, etc.) | [CLI](https://docs.praison.ai/cli/knowledge) | [📖](https://docs.praison.ai/api/praisonai/knowledge-query-engine-api) |

</details>

<details>
<summary><strong>🔬 Research & Intelligence</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Deep Research Agents | [Example](examples/python/agents/research-agent.py) | [📖](https://docs.praison.ai/agents/deep-research) |
| Query Rewriter Agent | [Example](examples/python/agents/query-rewriter-agent.py) | [📖](https://docs.praison.ai/agents/query-rewriter) |
| Native Web Search | [Example](examples/python/agents/websearch-agent.py) | [📖](https://docs.praison.ai/agents/websearch) |
| Built-in Search Tools | [Example](examples/python/agents/websearch-agent.py) | [📖](https://docs.praison.ai/tools/tavily) |
| Unified Web Search | [Example](src/praisonai-agents/examples/web_search_example.py) | [📖](https://docs.praison.ai/tools/web-search) |
| Web Fetch (Anthropic) | [Example](examples/python/agents/web-fetch-agent.py) | [📖](https://docs.praison.ai/features/model-capabilities) |

</details>

<details>
<summary><strong>📋 Planning & Execution</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Planning Mode | [Example](examples/python/agents/planning-agent.py) | [📖](https://docs.praison.ai/features/planning-mode) |
| Planning Tools | [Example](examples/python/agents/planning-agent.py) | [📖](https://docs.praison.ai/features/planning-mode) |
| Planning Reasoning | [Example](examples/python/agents/planning-agent.py) | [📖](https://docs.praison.ai/features/planning-mode) |
| Prompt Chaining | [Example](examples/python/general/prompt_chaining.py) | [📖](https://docs.praison.ai/features/promptchaining) |
| Evaluator Optimiser | [Example](examples/python/general/evaluator-optimiser.py) | [📖](https://docs.praison.ai/features/evaluator-optimiser) |
| Orchestrator Workers | [Example](examples/python/general/orchestrator-workers.py) | [📖](https://docs.praison.ai/features/orchestrator-worker) |

</details>

<details>
<summary><strong>👥 Specialized Agents</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Data Analyst Agent | [Example](examples/python/agents/data-analyst-agent.py) | [📖](https://docs.praison.ai/agents/data-analyst) |
| Finance Agent | [Example](examples/python/agents/finance-agent.py) | [📖](https://docs.praison.ai/agents/finance) |
| Shopping Agent | [Example](examples/python/agents/shopping-agent.py) | [📖](https://docs.praison.ai/agents/shopping) |
| Recommendation Agent | [Example](examples/python/agents/recommendation-agent.py) | [📖](https://docs.praison.ai/agents/recommendation) |
| Wikipedia Agent | [Example](examples/python/agents/wikipedia-agent.py) | [📖](https://docs.praison.ai/agents/wikipedia) |
| Programming Agent | [Example](examples/python/agents/programming-agent.py) | [📖](https://docs.praison.ai/agents/programming) |
| Math Agents | [Example](examples/python/agents/math-agent.py) | [📖](https://docs.praison.ai/features/mathagent) |
| Markdown Agent | [Example](examples/python/agents/markdown-agent.py) | [📖](https://docs.praison.ai/agents/markdown) |
| Prompt Expander Agent | [Example](examples/python/agents/prompt-expander-agent.py) | [📖](https://docs.praison.ai/agents/prompt-expander) |

</details>

<details>
<summary><strong>🎨 Media & Multimodal</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Image Generation Agent | [Example](examples/python/image/image-agent.py) | [📖](https://docs.praison.ai/features/image-generation) |
| Image to Text Agent | [Example](examples/python/agents/image-to-text-agent.py) | [📖](https://docs.praison.ai/agents/image-to-text) |
| Video Agent | [Example](examples/python/agents/video-agent.py) | [📖](https://docs.praison.ai/agents/video) |
| Camera Integration | [Example](examples/python/camera/) | [📖](https://docs.praison.ai/features/camera-integration) |

</details>

<details>
<summary><strong>🔌 Protocols & Integration</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| MCP Transports | [Example](examples/python/mcp/mcp-transports-overview.py) | [📖](https://docs.praison.ai/mcp/transports) |
| WebSocket MCP | [Example](examples/python/mcp/websocket-mcp.py) | [📖](https://docs.praison.ai/mcp/sse-transport) |
| MCP Security | [Example](examples/python/mcp/mcp-security.py) | [📖](https://docs.praison.ai/mcp/transports) |
| MCP Resumability | [Example](examples/python/mcp/mcp-resumability.py) | [📖](https://docs.praison.ai/mcp/sse-transport) |
| MCP Config Management | [Docs](https://docs.praison.ai/cli/mcp) | [📖](https://docs.praison.ai/cli/mcp) |
| LangChain Integrated Agents | [Example](examples/python/general/langchain_example.py) | [📖](https://docs.praison.ai/features/langchain) |

</details>

<details>
<summary><strong>🛡️ Safety & Control</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Guardrails | [Example](examples/python/guardrails/comprehensive-guardrails-example.py) | [📖](https://docs.praison.ai/features/guardrails) |
| Human Approval | [Example](examples/python/general/human_approval_example.py) | [📖](https://docs.praison.ai/features/approval) |
| Rules & Instructions | [Docs](https://docs.praison.ai/features/rules) | [📖](https://docs.praison.ai/features/rules) |

</details>

<details>
<summary><strong>⚙️ Advanced Features</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Async & Parallel Processing | [Example](examples/python/general/async_example.py) | [📖](https://docs.praison.ai/features/async) |
| Parallelisation | [Example](examples/python/general/parallelisation.py) | [📖](https://docs.praison.ai/features/parallelisation) |
| Repetitive Agents | [Example](examples/python/concepts/repetitive-agents.py) | [📖](https://docs.praison.ai/features/repetitive) |
| Agent Handoffs | [Example](examples/python/handoff/handoff_basic.py) | [📖](https://docs.praison.ai/features/handoffs) |
| Stateful Agents | [Example](examples/python/stateful/workflow-state-example.py) | [📖](https://docs.praison.ai/features/stateful-agents) |
| Autonomous Workflow | [Example](examples/python/general/autonomous-agent.py) | [📖](https://docs.praison.ai/features/autonomous-workflow) |
| Structured Output Agents | [Example](examples/python/general/structured_agents_example.py) | [📖](https://docs.praison.ai/features/structured) |
| Model Router | [Example](examples/python/agents/router-agent-cost-optimization.py) | [📖](https://docs.praison.ai/features/model-router) |
| Prompt Caching | [Example](examples/python/agents/prompt-caching-agent.py) | [📖](https://docs.praison.ai/features/model-capabilities) |
| Fast Context | [Example](examples/context/00_agent_fast_context_basic.py) | [📖](https://docs.praison.ai/features/fast-context) |

</details>

<details>
<summary><strong>🛠️ Tools & Configuration</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| 100+ Custom Tools | [Example](examples/python/general/tools_example.py) | [📖](https://docs.praison.ai/tools/tools) |
| YAML Configuration | [Example](examples/cookbooks/yaml/secondary_market_research_agents.yaml) | [📖](https://docs.praison.ai/developers/agents-playbook) |
| 100+ LLM Support | [Example](examples/python/providers/openai/openai_gpt4_example.py) | [📖](https://docs.praison.ai/models) |
| Callback Agents | [Example](examples/python/general/advanced-callback-systems.py) | [📖](https://docs.praison.ai/features/callbacks) |
| Hooks | [Example](examples/python/hooks/hooks_example.py) | [📖](https://docs.praison.ai/features/hooks) |
| Middleware System | [Example](examples/middleware/basic_middleware.py) | [📖](https://docs.praison.ai/features/middleware) |
| Configurable Model | [Example](examples/middleware/configurable_model.py) | [📖](https://docs.praison.ai/features/configurable-model) |
| Rate Limiter | [Example](examples/middleware/rate_limiter.py) | [📖](https://docs.praison.ai/features/rate-limiter) |
| Injected Tool State | [Example](examples/middleware/injected_state.py) | [📖](https://docs.praison.ai/features/injected-state) |
| Shadow Git Checkpoints | [Example](examples/checkpoints/basic_checkpoint.py) | [📖](https://docs.praison.ai/features/checkpoints) |
| Background Tasks | [Example](examples/background/basic_background.py) | [📖](https://docs.praison.ai/features/background-tasks) |
| Policy Engine | [Example](examples/policy/basic_policy.py) | [📖](https://docs.praison.ai/features/policy-engine) |
| Thinking Budgets | [Example](examples/thinking/basic_thinking.py) | [📖](https://docs.praison.ai/features/thinking-budgets) |
| Output Styles | [Example](examples/output/basic_output.py) | [📖](https://docs.praison.ai/features/output-styles) |
| Context Compaction | [Example](examples/compaction/basic_compaction.py) | [📖](https://docs.praison.ai/features/context-compaction) |

</details>

<details>
<summary><strong>📊 Monitoring & Management</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Sessions Management | [Example](examples/python/sessions/comprehensive-session-management.py) | [📖](https://docs.praison.ai/features/sessions) |
| Auto-Save Sessions | [Docs](https://docs.praison.ai/cli/session) | [📖](https://docs.praison.ai/cli/session) |
| History in Context | [Docs](https://docs.praison.ai/cli/session) | [📖](https://docs.praison.ai/cli/session) |
| Telemetry | [Example](examples/python/telemetry/production-telemetry-example.py) | [📖](https://docs.praison.ai/features/telemetry) |
| Project Docs (.praison/docs/) | [Docs](https://docs.praison.ai/cli/docs) | [📖](https://docs.praison.ai/cli/docs) |
| AI Commit Messages | [Docs](https://docs.praison.ai/cli/commit) | [📖](https://docs.praison.ai/cli/commit) |
| @Mentions in Prompts | [Docs](https://docs.praison.ai/cli/mentions) | [📖](https://docs.praison.ai/cli/mentions) |

</details>

<details>
<summary><strong>🖥️ CLI Features</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Slash Commands | [Example](examples/python/cli/slash_commands_example.py) | [📖](https://docs.praison.ai/cli/slash-commands) |
| Autonomy Modes | [Example](examples/python/cli/autonomy_modes_example.py) | [📖](https://docs.praison.ai/cli/autonomy-modes) |
| Cost Tracking | [Example](examples/python/cli/cost_tracking_example.py) | [📖](https://docs.praison.ai/cli/cost-tracking) |
| Repository Map | [Example](examples/python/cli/repo_map_example.py) | [📖](https://docs.praison.ai/cli/repo-map) |
| Interactive TUI | [Example](examples/python/cli/interactive_tui_example.py) | [📖](https://docs.praison.ai/cli/interactive-tui) |
| Git Integration | [Example](examples/python/cli/git_integration_example.py) | [📖](https://docs.praison.ai/cli/git-integration) |
| Sandbox Execution | [Example](examples/python/cli/sandbox_execution_example.py) | [📖](https://docs.praison.ai/cli/sandbox-execution) |
| CLI Compare | [Example](examples/compare/cli_compare_basic.py) | [📖](https://docs.praison.ai/cli/compare) |
| Profile/Benchmark | [Docs](https://docs.praison.ai/cli/profile) | [📖](https://docs.praison.ai/cli/profile) |
| Auto Mode | [Docs](https://docs.praison.ai/cli/auto) | [📖](https://docs.praison.ai/cli/auto) |
| Init | [Docs](https://docs.praison.ai/cli/init) | [📖](https://docs.praison.ai/cli/init) |
| File Input | [Docs](https://docs.praison.ai/cli/file-input) | [📖](https://docs.praison.ai/cli/file-input) |
| Final Agent | [Docs](https://docs.praison.ai/cli/final-agent) | [📖](https://docs.praison.ai/cli/final-agent) |
| Max Tokens | [Docs](https://docs.praison.ai/cli/max-tokens) | [📖](https://docs.praison.ai/cli/max-tokens) |

</details>

<details>
<summary><strong>🧪 Evaluation</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Accuracy Evaluation | [Example](examples/eval/accuracy_example.py) | [📖](https://docs.praison.ai/cli/eval) |
| Performance Evaluation | [Example](examples/eval/performance_example.py) | [📖](https://docs.praison.ai/cli/eval) |
| Reliability Evaluation | [Example](examples/eval/reliability_example.py) | [📖](https://docs.praison.ai/cli/eval) |
| Criteria Evaluation | [Example](examples/eval/criteria_example.py) | [📖](https://docs.praison.ai/cli/eval) |

</details>

<details>
<summary><strong>🎯 Agent Skills</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Skills Management | [Example](examples/skills/basic_skill_usage.py) | [📖](https://docs.praison.ai/features/skills) |
| Custom Skills | [Example](examples/skills/custom_skill_example.py) | [📖](https://docs.praison.ai/features/skills) |

</details>

<details>
<summary><strong>⏰ 24/7 Scheduling</strong></summary>

| Feature | Code | Docs |
|---------|:----:|:----:|
| Agent Scheduler | [Example](examples/python/scheduled_agents/news_checker_live.py) | [📖](https://docs.praison.ai/cli/scheduler) |

</details>

---

## 🌐 Supported Providers

PraisonAI supports 100+ LLM providers through seamless integration:

<details>
<summary><strong>View all 24 providers</strong></summary>

| Provider | Example |
|----------|:-------:|
| OpenAI | [Example](examples/python/providers/openai/openai_gpt4_example.py) |
| Anthropic | [Example](examples/python/providers/anthropic/anthropic_claude_example.py) |
| Google Gemini | [Example](examples/python/providers/google/google_gemini_example.py) |
| Ollama | [Example](examples/python/providers/ollama/ollama-agents.py) |
| Groq | [Example](examples/python/providers/groq/kimi_with_groq_example.py) |
| DeepSeek | [Example](examples/python/providers/deepseek/deepseek_example.py) |
| xAI Grok | [Example](examples/python/providers/xai/xai_grok_example.py) |
| Mistral | [Example](examples/python/providers/mistral/mistral_example.py) |
| Cohere | [Example](examples/python/providers/cohere/cohere_example.py) |
| Perplexity | [Example](examples/python/providers/perplexity/perplexity_example.py) |
| Fireworks | [Example](examples/python/providers/fireworks/fireworks_example.py) |
| Together AI | [Example](examples/python/providers/together/together_ai_example.py) |
| OpenRouter | [Example](examples/python/providers/openrouter/openrouter_example.py) |
| HuggingFace | [Example](examples/python/providers/huggingface/huggingface_example.py) |
| Azure OpenAI | [Example](examples/python/providers/azure/azure_openai_example.py) |
| AWS Bedrock | [Example](examples/python/providers/aws/aws_bedrock_example.py) |
| Google Vertex | [Example](examples/python/providers/vertex/vertex_example.py) |
| Databricks | [Example](examples/python/providers/databricks/databricks_example.py) |
| Cloudflare | [Example](examples/python/providers/cloudflare/cloudflare_example.py) |
| AI21 | [Example](examples/python/providers/ai21/ai21_example.py) |
| Replicate | [Example](examples/python/providers/replicate/replicate_example.py) |
| SageMaker | [Example](examples/python/providers/sagemaker/sagemaker_example.py) |
| Moonshot | [Example](examples/python/providers/moonshot/moonshot_example.py) |
| vLLM | [Example](examples/python/providers/vllm/vllm_example.py) |

</details>

---

## 📘 Using Python Code

### 1. Single Agent

```python
from praisonaiagents import Agent
agent = Agent(instructions="Your are a helpful AI assistant")
agent.start("Write a movie script about a robot in Mars")
```

### 2. Multi Agents

```python
from praisonaiagents import Agent, Agents

research_agent = Agent(instructions="Research about AI")
summarise_agent = Agent(instructions="Summarise research agent's findings")
agents = Agents(agents=[research_agent, summarise_agent])
agents.start()
```

### 3. MCP (Model Context Protocol)

```python
from praisonaiagents import Agent, MCP

# stdio - Local NPX/Python servers
agent = Agent(tools=MCP("npx @modelcontextprotocol/server-memory"))

# Streamable HTTP - Production servers
agent = Agent(tools=MCP("https://api.example.com/mcp"))

# WebSocket - Real-time bidirectional
agent = Agent(tools=MCP("wss://api.example.com/mcp", auth_token="token"))

# With environment variables
agent = Agent(
    tools=MCP(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": "your-key"}
    )
)
```

> 📖 [Full MCP docs](https://docs.praison.ai/mcp/transports) — stdio, HTTP, WebSocket, SSE transports

### 4. Custom Tools

```python
from praisonaiagents import Agent, tool

@tool
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

@tool
def calculate(expression: str) -> float:
    """Evaluate a math expression."""
    return eval(expression)

agent = Agent(
    instructions="You are a helpful assistant",
    tools=[search, calculate]
)
agent.start("Search for AI news and calculate 15*4")
```

> 📖 [Full tools docs](https://docs.praison.ai/tools/tools) — BaseTool, tool packages, 100+ built-in tools

### 5. Persistence (Databases)

```python
from praisonaiagents import Agent, db

agent = Agent(
    name="Assistant",
    db=db(database_url="postgresql://localhost/mydb"),
    session_id="my-session"
)
agent.chat("Hello!")  # Auto-persists messages, runs, traces
```

> 📖 [Full persistence docs](https://docs.praison.ai/databases/overview) — PostgreSQL, MySQL, SQLite, MongoDB, Redis, and 20+ more

---

## 🎯 CLI Quick Reference

| Category | Commands |
|----------|----------|
| **Execution** | `praisonai`, `--auto`, `--interactive`, `--chat` |
| **Research** | `research`, `--query-rewrite`, `--deep-research` |
| **Planning** | `--planning`, `--planning-tools`, `--planning-reasoning` |
| **Workflows** | `workflow run`, `workflow list`, `workflow auto` |
| **Memory** | `memory show`, `memory add`, `memory search`, `memory clear` |
| **Knowledge** | `knowledge add`, `knowledge query`, `knowledge list` |
| **Sessions** | `session list`, `session resume`, `session delete` |
| **Tools** | `tools list`, `tools info`, `tools search` |
| **MCP** | `mcp list`, `mcp create`, `mcp enable` |
| **Development** | `commit`, `docs`, `checkpoint`, `hooks` |
| **Scheduling** | `schedule start`, `schedule list`, `schedule stop` |

> 📖 [Full CLI reference](https://docs.praison.ai/cli/cli-reference)

---

## 💻 Using JavaScript Code

```bash
npm install praisonai
export OPENAI_API_KEY=xxxxxxxxxxxxxxxxxxxxxx
```

```javascript
const { Agent } = require('praisonai');
const agent = new Agent({ instructions: 'You are a helpful AI assistant' });
agent.start('Write a movie script about a robot in Mars');
```

![PraisonAI CLI Demo](docs/demo/praisonai-cli-demo.gif)

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=MervinPraison/PraisonAI&type=Date)](https://docs.praison.ai)

---

## 🎓 Video Tutorials

Learn PraisonAI through our comprehensive video series:

<details>
<summary><strong>View all 22 video tutorials</strong></summary>

| Topic | Video |
|-------|--------|
| AI Agents with Self Reflection | [![Self Reflection](https://img.youtube.com/vi/vLXobEN2Vc8/0.jpg)](https://www.youtube.com/watch?v=vLXobEN2Vc8) |
| Reasoning Data Generating Agent | [![Reasoning Data](https://img.youtube.com/vi/fUT332Y2zA8/0.jpg)](https://www.youtube.com/watch?v=fUT332Y2zA8) |
| AI Agents with Reasoning | [![Reasoning](https://img.youtube.com/vi/KNDVWGN3TpM/0.jpg)](https://www.youtube.com/watch?v=KNDVWGN3TpM) |
| Multimodal AI Agents | [![Multimodal](https://img.youtube.com/vi/hjAWmUT1qqY/0.jpg)](https://www.youtube.com/watch?v=hjAWmUT1qqY) |
| AI Agents Workflow | [![Workflow](https://img.youtube.com/vi/yWTH44QPl2A/0.jpg)](https://www.youtube.com/watch?v=yWTH44QPl2A) |
| Async AI Agents | [![Async](https://img.youtube.com/vi/VhVQfgo00LE/0.jpg)](https://www.youtube.com/watch?v=VhVQfgo00LE) |
| Mini AI Agents | [![Mini](https://img.youtube.com/vi/OkvYp5aAGSg/0.jpg)](https://www.youtube.com/watch?v=OkvYp5aAGSg) |
| AI Agents with Memory | [![Memory](https://img.youtube.com/vi/1hVfVxvPnnQ/0.jpg)](https://www.youtube.com/watch?v=1hVfVxvPnnQ) |
| Repetitive Agents | [![Repetitive](https://img.youtube.com/vi/dAYGxsjDOPg/0.jpg)](https://www.youtube.com/watch?v=dAYGxsjDOPg) |
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
| Reasoning Extract Agents | [![Reasoning Extract](https://img.youtube.com/vi/2PPamsADjJA/0.jpg)](https://www.youtube.com/watch?v=2PPamsADjJA) |

</details>

---

## 👥 Contributing

We welcome contributions from the community! Here's how you can contribute:

1. **Fork on GitHub** - Use the "Fork" button on the [repository page](https://github.com/MervinPraison/PraisonAI)
2. **Clone your fork** - `git clone https://github.com/yourusername/praisonAI.git`
3. **Create a branch** - `git checkout -b new-feature`
4. **Make changes and commit** - `git commit -am "Add some feature"`
5. **Push to your fork** - `git push origin new-feature`
6. **Submit a pull request** - Via GitHub's web interface
7. **Await feedback** - From project maintainers

---

## 🔧 Development

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

### Bump and Release

```bash
# From project root - bumps version and releases in one command
python src/praisonai/scripts/bump_and_release.py 2.2.99

# With praisonaiagents dependency
python src/praisonai/scripts/bump_and_release.py 2.2.99 --agents 0.0.169

# Then publish
cd src/praisonai && uv publish
```

---

## ❓ FAQ & Troubleshooting

<details>
<summary><strong>ModuleNotFoundError: No module named 'praisonaiagents'</strong></summary>

Install the package:
```bash
pip install praisonaiagents
```

</details>

<details>
<summary><strong>API key not found / Authentication error</strong></summary>

Ensure your API key is set:
```bash
export OPENAI_API_KEY=your_key_here
```

For other providers, see [Environment Variables](#environment-variables).

</details>

<details>
<summary><strong>How do I use a local model (Ollama)?</strong></summary>

```bash
# Start Ollama server first
ollama serve

# Set environment variable
export OPENAI_BASE_URL=http://localhost:11434/v1
```

See [Models docs](https://docs.praison.ai/models) for more details.

</details>

<details>
<summary><strong>How do I persist conversations to a database?</strong></summary>

Use the `db` parameter:
```python
from praisonaiagents import Agent, db

agent = Agent(
    name="Assistant",
    db=db(database_url="postgresql://localhost/mydb"),
    session_id="my-session"
)
```

See [Persistence docs](https://docs.praison.ai/databases/overview) for supported databases.

</details>

<details>
<summary><strong>How do I enable agent memory?</strong></summary>

```python
from praisonaiagents import Agent

agent = Agent(
    name="Assistant",
    memory=True,  # Enables file-based memory (no extra deps!)
    user_id="user123"
)
```

See [Memory docs](https://docs.praison.ai/concepts/memory) for more options.

</details>

<details>
<summary><strong>How do I run multiple agents together?</strong></summary>

```python
from praisonaiagents import Agent, Agents

agent1 = Agent(instructions="Research topics")
agent2 = Agent(instructions="Summarize findings")
agents = Agents(agents=[agent1, agent2])
agents.start()
```

See [Agents docs](https://docs.praison.ai/concepts/agents) for more examples.

</details>

<details>
<summary><strong>How do I use MCP tools?</strong></summary>

```python
from praisonaiagents import Agent, MCP

agent = Agent(
    tools=MCP("npx @modelcontextprotocol/server-memory")
)
```

See [MCP docs](https://docs.praison.ai/mcp/transports) for all transport options.

</details>

### Getting Help

- 📚 [Full Documentation](https://docs.praison.ai)
- 🐛 [Report Issues](https://github.com/MervinPraison/PraisonAI/issues)
- 💬 [Discussions](https://github.com/MervinPraison/PraisonAI/discussions)

---

<div align="center">
  <p><strong>Made with ❤️ by the PraisonAI Team</strong></p>
  <p>
    <a href="https://docs.praison.ai">Documentation</a> •
    <a href="https://github.com/MervinPraison/PraisonAI">GitHub</a> •
    <a href="https://github.com/MervinPraison/PraisonAI/issues">Issues</a>
  </p>
</div>
