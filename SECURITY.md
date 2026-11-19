# Security Policy

PraisonAI takes security seriously. We appreciate responsible disclosure from researchers and users.

This page says how to report a vulnerability and what we treat as one. The
[threat model](https://docs.praison.ai/docs/features/threat-model) explains the
trust boundaries in more detail.

## Supported packages

| Package | Registry | Source path |
|---------|----------|-------------|
| `praisonaiagents` | [PyPI](https://pypi.org/project/praisonaiagents/) | `src/praisonai-agents/` |
| `praisonai` | [PyPI](https://pypi.org/project/praisonai/) | `src/praisonai/` |
| `praisonai-code` | [PyPI](https://pypi.org/project/praisonai-code/) | `src/praisonai-code/` |
| `praisonai-bot` | [PyPI](https://pypi.org/project/praisonai-bot/) | `src/praisonai-bot/` |
| `praisonai-train` | [PyPI](https://pypi.org/project/praisonai-train/) | `src/praisonai-train/` |
| `praisonai-browser` | [PyPI](https://pypi.org/project/praisonai-browser/) | `src/praisonai-browser/` |
| `praisonai-mcp` | [PyPI](https://pypi.org/project/praisonai-mcp/) | `src/praisonai-mcp/` |
| `praisonai-sandbox` | [PyPI](https://pypi.org/project/praisonai-sandbox/) | `src/praisonai-sandbox/` |
| `praisonai-deploy` | [PyPI](https://pypi.org/project/praisonai-deploy/) | `src/praisonai-deploy/` |
| `praisonai` | [npm](https://www.npmjs.com/package/praisonai) | `src/praisonai-ts/` |
| PraisonAI Desktop | [GitHub releases](https://github.com/MervinPraison/PraisonAI/releases/latest) | `src/praisonai-desktop/` |

Security fixes ship in a new release of the affected package. Only the latest
release is supported: please reproduce on it before reporting, and upgrade to
receive fixes.

Report issues against the **specific package** where the vulnerability exists. A platform-only issue does not necessarily affect the core SDK, and vice versa.

### Packages maintained in their own repositories

These are versioned and released independently of the SDK. Report their
vulnerabilities in their own repository, not here:

- `praisonai-platform`:
  [MervinPraison/praisonai-platform](https://github.com/MervinPraison/praisonai-platform)
  ([report](https://github.com/MervinPraison/praisonai-platform/security/advisories/new))
- PraisonAI UI (`aiui`):
  [MervinPraison/PraisonAIUI](https://github.com/MervinPraison/PraisonAIUI)
  ([report](https://github.com/MervinPraison/PraisonAIUI/security/advisories/new))

## Trust boundaries

**Trusted:** the operator who runs PraisonAI, their user-level configuration
and environment variables, and code the operator chooses to install or
register (packages, plugins, tools, hooks).

**Untrusted:** model output, tool results, fetched web content, project files
in a repository the operator did not write (for example a cloned repository),
and network peers that connect to a PraisonAI server.

A vulnerability is a way for untrusted input to cross into the trusted side
without the operator's consent: for example to run code, read or write files
outside what the operator allowed, reach secrets, or act through a server
without authorisation.

## Not a security boundary

The following reduce accidents. They do not contain hostile code, and a way
around them is not a vulnerability:

- **Built-in Python code execution** (`ExecutionConfig(code_mode="safe" | "unsafe" | "isolated")`).
  All three modes run code on the host as the same OS user, either in the
  agent process or in a local subprocess. Restricted builtins, import filters
  and resource limits are guard rails, not isolation.
  The same holds for `PythonTools` and for inline Python steps in job
  workflows (`praisonai-code`): they run on the host as the operator.
- **The TypeScript `codeMode` tool**, which runs code in a Node.js `vm` context.
- **String-based shell command filters** (allow or deny patterns over a
  command line). This includes the CLI `SandboxExecutor` in `praisonai-code`
  and in the TypeScript SDK: all of its modes (`basic`, `strict`,
  `network-isolated`) check the command text and then run it on the host. The
  mode names describe which commands are filtered, not isolation.

To run untrusted or model-written code, use an isolating backend from
[`praisonai-sandbox`](src/praisonai-sandbox/): Docker, Sandlock (Linux), E2B,
Modal, Daytona or Novita. Its `subprocess` backend and the `local` compute
provider (`LocalCompute`) run on the host and are not isolation either.

A way around the guard rails above is a hardening bug. Please open a normal
public issue for it.

## Network servers

Agents can be served over HTTP, MCP, A2A and AG-UI. Bind addresses differ
between entry points, and some default to all interfaces. We recommend:

- Bind to `127.0.0.1` unless the server must be reachable from other machines.
- Put authentication in front of anything you expose: a token, or a reverse
  proxy that authenticates.
- `Agent.launch()` over HTTP binds to `127.0.0.1` by default. On any other
  address it requires a bearer token: set `PRAISONAI_LAUNCH_AUTH_TOKEN`, or one
  is generated and printed at start-up.

## In scope

- Authentication, authorisation, and multi-tenant isolation (e.g. workspace boundaries)
- Untrusted input (see [Trust boundaries](#trust-boundaries)) that leads to code execution, file access, or secret exposure without operator consent
- Escape from an isolating `praisonai-sandbox` backend
- SSRF, injection, and unsafe deserialisation in shipped code
- MCP, gateway, and bot/webhook integrations
- Secrets handling, JWT/session configuration, and default credentials
- Supply-chain issues in published package artefacts

## Out of scope

- Ways around the guard rails listed under [Not a security boundary](#not-a-security-boundary) (please open a public issue)
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

### What a report needs

- **A working proof of concept** against the latest release, in its default
  configuration. If it needs a non-default setting, say which and why a user
  would set it.
- **One report per root cause.** Several entry points that reach the same flaw
  belong in one report.
- **A way around an earlier fix** is a comment on the original advisory, not a
  new report.
- Reports that only restate the output of a scanner or an AI tool, without a
  tested proof of concept, are closed.

## What to expect

Response targets:

| Step | Target |
|------|--------|
| Acknowledge the report | 2 working days |
| Decision (accepted, duplicate, out of scope, or more information needed) | 14 days |
| Fix released for a confirmed high or critical issue | 30 days |

1. **Triage**: we validate the report and assign a disposition (`real`, `duplicate`, `wontfix`, etc.)
2. **Severity**: assigned by the maintainers with CVSS 3.1, scored against the default configuration
3. **Fix**: minimal, backward-compatible patch on `main` where appropriate
4. **Release**: patched version published to PyPI/npm **before** the advisory is published
5. **Advisory**: GitHub Security Advisory with reporter credit and CVE where applicable

## Resources

- **Threat model:** https://docs.praison.ai/docs/features/threat-model
- **Repository:** https://github.com/MervinPraison/PraisonAI
- **Documentation:** https://docs.praison.ai
- **Website:** https://praison.ai
- **Advisories:** https://github.com/MervinPraison/PraisonAI/security/advisories

## Maintainer workflow

Contributors and agents handling audits should follow:

`src/praisonai-agents/.agent/workflows/security-audit.md`
