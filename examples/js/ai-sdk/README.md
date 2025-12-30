# AI SDK Examples

Examples demonstrating the AI SDK integration in PraisonAI TypeScript.

## Prerequisites

```bash
npm install praisonai ai @ai-sdk/openai @ai-sdk/anthropic @ai-sdk/google zod
```

## Environment Variables

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=AIza...
```

## Examples

| File | Description |
|------|-------------|
| `basic-chat.ts` | Simple text generation |
| `streaming.ts` | Streaming text output |
| `tool-calling.ts` | Function/tool calling |
| `multi-provider.ts` | Using multiple providers |
| `structured-output.ts` | JSON schema output |
| `multi-agent.ts` | Multi-agent attribution |

## Running Examples

```bash
npx ts-node basic-chat.ts
npx ts-node streaming.ts
npx ts-node tool-calling.ts
```

## More Information

- [AI SDK Documentation](https://docs.praisonai.com/docs/js/ai-sdk)
- [AI SDK CLI](https://docs.praisonai.com/docs/js/ai-sdk-cli)
