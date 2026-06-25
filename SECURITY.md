# Security Policy

PraisonAI takes security seriously. We appreciate responsible disclosure from researchers and users.

## Supported packages

| Package | Registry | Source path |
|---------|----------|-------------|
| `praisonaiagents` | [PyPI](https://pypi.org/project/praisonaiagents/) | `src/praisonai-agents/` |
| `praisonai` | [PyPI](https://pypi.org/project/praisonai/) | `src/praisonai/` |
| `praisonai-platform` | [PyPI](https://pypi.org/project/praisonai-platform/) | `src/praisonai-platform/` |
| `praisonai` | [npm](https://www.npmjs.com/package/praisonai) | `src/praisonai-ts/` |

Report issues against the **specific package** where the vulnerability exists. A platform-only issue does not necessarily affect the core SDK, and vice versa.

## In scope

- Authentication, authorisation, and multi-tenant isolation (e.g. workspace boundaries)
- Tool execution, sandbox escape, and code execution paths
- SSRF, injection, and unsafe deserialisation in shipped code
- MCP, gateway, and bot/webhook integrations
- Secrets handling, JWT/session configuration, and default credentials
- Supply-chain issues in published package artefacts

## Out of scope

- Issues in forks or deployments not maintained in [MervinPraison/PraisonAI](https://github.com/MervinPraison/PraisonAI)
- Vulnerabilities requiring physical access or fully compromised operator machines
- Reports against versions no longer published or without a supported upgrade path
- Theoretical issues with no practical impact in documented, supported configurations
- Behaviour covered by an explicit, documented opt-out (e.g. dev-only env vars)

## How to report

**Preferred:** open a **private** security advisory:

[https://github.com/MervinPraison/PraisonAI/security/advisories/new](https://github.com/MervinPraison/PraisonAI/security/advisories/new)

Include:

1. Affected package and version
2. Clear reproduction steps
3. Impact assessment (confidentiality, integrity, availability)
4. Suggested fix (optional)

Please allow reasonable time for triage and a patched release before public disclosure.

## What to expect

1. **Triage** — we validate the report and assign a disposition (`real`, `duplicate`, `wontfix`, etc.)
2. **Fix** — minimal, backward-compatible patch on `main` where appropriate
3. **Release** — patched version published to PyPI/npm **before** the advisory is published
4. **Advisory** — GitHub Security Advisory with reporter credit and CVE where applicable

## Resources

- **Repository:** https://github.com/MervinPraison/PraisonAI
- **Documentation:** https://docs.praison.ai
- **Website:** https://praison.ai
- **Advisories:** https://github.com/MervinPraison/PraisonAI/security/advisories

## Maintainer workflow

Contributors and agents handling audits should follow:

`src/praisonai-agents/.agent/workflows/security-audit.md`
