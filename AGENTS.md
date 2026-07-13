# Agent Instructions

You are working on the PraisonAI project.

## Project Guidelines
- Follow the existing code style and conventions
- Be concise and helpful in responses  
- Test implementation thoroughly
- Ensure backward compatibility with existing APIs
- Follow protocol-driven design: core protocols in `praisonaiagents/`, agentic terminal CLI in `praisonai-code/`, bot/channel and heavy implementations in `praisonai/`
- Preserve old `praisonai.cli.*` import paths via shims when changing moved CLI code (see §2.3 in `src/praisonai-agents/AGENTS.md`)
- When reviewing a PR or an issue, evaluate whether the change addresses a framework concern or a user goal, and design its surface (params, naming, defaults) accordingly