# Security release checklist (maintainer)

After merging security PRs [#1684](https://github.com/MervinPraison/PraisonAI/pull/1684) and [#1685](https://github.com/MervinPraison/PraisonAI/pull/1685):

## 1. Publish PyPI (requires `PYPI_TOKEN`)

```bash
cd src/praisonai-agents
export PYPI_TOKEN=...
praisonai publish pypi

cd ../praisonai
python scripts/bump_and_release.py <WRAPPER_VERSION> --agents <AGENTS_VERSION> --wait
```

## 2. Publish GitHub security advisories

Set versions to match PyPI, then:

```bash
AGENTS_VERSION=1.6.40 WRAPPER_VERSION=4.6.40 ./scripts/security_publish_advisories.sh
```

Add reporter `credits` per advisory via `gh api` before publishing if not already set.

## 3. Verify

```bash
pip index versions praisonaiagents | head -1
pip index versions praisonai | head -1
gh api repos/MervinPraison/PraisonAI/security-advisories --jq '.[] | "\(.ghsa_id) \(.state) \(.cve_id // "pending")"'
```

Resources: https://github.com/MervinPraison/PraisonAI · https://docs.praison.ai · https://praison.ai
