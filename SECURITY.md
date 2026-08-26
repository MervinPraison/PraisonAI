# Security Policy

PraisonAI takes security seriously. We appreciate responsible disclosure from researchers and users.

## Supported packages

| Package | Registry | Source path |
|---------|----------|-------------|
| `praisonaiagents` | [PyPI](https://pypi.org/project/praisonaiagents/) | `src/praisonai-agents/` |
| `praisonai` | [PyPI](https://pypi.org/project/praisonai/) | `src/praisonai/` |
| `praisonai` | [npm](https://www.npmjs.com/package/praisonai) | [praisonai-js](https://github.com/MervinPraison/praisonai-js) (canonical); mirrored at `src/praisonai-ts/` |

Report npm/TypeScript vulnerabilities on **PraisonAI** (hub intake) or [praisonai-js](https://github.com/MervinPraison/praisonai-js). Fixes land in praisonai-js first.

Report issues against the **specific package** where the vulnerability exists. A platform-only issue does not necessarily affect the core SDK, and vice versa.

### Packages maintained in their own repositories

`praisonai-platform` now lives at
[MervinPraison/PraisonAI-Platform](https://github.com/MervinPraison/PraisonAI-Platform).
Report platform vulnerabilities through
[that repository's advisories](https://github.com/MervinPraison/PraisonAI-Platform/security/advisories/new),
not here — it is versioned and released independently of the SDK.

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
