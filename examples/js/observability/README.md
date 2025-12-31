# Observability Examples

Examples demonstrating how to use observability integrations with PraisonAI TypeScript.

## Setup

```bash
# Install dependencies
cd /path/to/praisonai-ts
pnpm install

# Set API keys for observability tools
export LANGFUSE_SECRET_KEY=sk-...
export LANGFUSE_PUBLIC_KEY=pk-...
# Or use built-in tools (no API key needed)
```

## Examples

| File | Description |
|------|-------------|
| `basic-tracing.ts` | Basic tracing with memory adapter |
| `langfuse-integration.ts` | Langfuse observability integration |
| `multi-agent-attribution.ts` | Track agent_id/run_id across agents |
| `switchable-tools.ts` | Switch between observability tools via env |

## Running Examples

```bash
# Run with ts-node or tsx
npx tsx examples/js/observability/basic-tracing.ts
npx tsx examples/js/observability/multi-agent-attribution.ts

# With Langfuse (requires API keys)
LANGFUSE_SECRET_KEY=sk-... npx tsx examples/js/observability/langfuse-integration.ts
```

## Supported Tools

| Tool | Env Variable | Package |
|------|--------------|---------|
| Langfuse | `LANGFUSE_SECRET_KEY` | `langfuse` |
| LangSmith | `LANGCHAIN_API_KEY` | `langsmith` |
| LangWatch | `LANGWATCH_API_KEY` | `langwatch` |
| Arize | `ARIZE_API_KEY` | `arize-phoenix` |
| Axiom | `AXIOM_TOKEN` | `@axiomhq/js` |
| Braintrust | `BRAINTRUST_API_KEY` | `braintrust` |
| Helicone | `HELICONE_API_KEY` | `@helicone/helicone` |
| Console | (none) | built-in |
| Memory | (none) | built-in |
