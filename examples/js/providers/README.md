# Provider Examples

Examples demonstrating how to use different LLM providers with PraisonAI TypeScript.

## Setup

```bash
# Install dependencies
cd /path/to/praisonai-ts
pnpm install

# Set API keys
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=AIza...
```

## Examples

| File | Description |
|------|-------------|
| `multi-provider.ts` | Use multiple providers in one workflow |
| `openai-compatible.ts` | Use OpenAI-compatible APIs (LM Studio, etc.) |
| `local-ollama.ts` | Use local Ollama models |
| `provider-selection.ts` | Dynamic provider selection based on task |

## Running Examples

```bash
# Run with ts-node or tsx
npx tsx examples/js/providers/multi-provider.ts
npx tsx examples/js/providers/openai-compatible.ts
npx tsx examples/js/providers/local-ollama.ts
```

## Environment Variables

| Provider | Variable | Example |
|----------|----------|---------|
| OpenAI | `OPENAI_API_KEY` | `sk-...` |
| Anthropic | `ANTHROPIC_API_KEY` | `sk-ant-...` |
| Google | `GOOGLE_API_KEY` | `AIza...` |
| xAI | `XAI_API_KEY` | `xai-...` |
| Groq | `GROQ_API_KEY` | `gsk_...` |
| Mistral | `MISTRAL_API_KEY` | `...` |
| DeepSeek | `DEEPSEEK_API_KEY` | `...` |
| Ollama | `OLLAMA_BASE_URL` | `http://localhost:11434` |
