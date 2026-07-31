# praisonai-deploy

Deployment tooling for PraisonAI — API servers, Docker images, and cloud providers (AWS, Azure, GCP).

## Install

```bash
pip install praisonai-deploy
pip install "praisonai-deploy[api]"   # Flask API server generation
pip install "praisonai[deploy]"       # full umbrella with wrapper shims
```

## CLI

```bash
praisonai deploy run --file agents.yaml
praisonai deploy doctor --all
praisonai deploy validate --file agents.yaml
praisonai deploy plan --file agents.yaml
praisonai deploy status --file agents.yaml
praisonai deploy destroy --file agents.yaml --yes
praisonai deploy docker agents.yaml --tag v1
praisonai deploy aws agents.yaml --region us-east-1
```

Standalone console script:

```bash
praisonai-deploy --help
```

## Python API

```python
from praisonai_deploy import Deploy

deploy = Deploy.from_yaml("agents.yaml")
result = deploy.deploy()
status = deploy.status()
```

Legacy import paths (`praisonai.deploy.*`) remain available when the `praisonai` wrapper is installed.

## Runtime dependency (generated servers)

Generated API servers and Docker images install **`praisonai`** (full wrapper) at runtime — they embed `from praisonai import PraisonAI`. The deploy package owns orchestration (generate, build, plan, doctor); containers need `pip install praisonai flask gunicorn`.

## Cloud provider notes

| Provider | Behaviour |
|----------|-----------|
| AWS ECS | Update-only path; greenfield deploy requires pre-existing VPC/service config |
| Azure | Container Apps create/update |
| GCP | Cloud Run create-or-update |

Host CLIs required: `docker`, `aws`, `az`, `gcloud` (no boto3/Azure SDK in this package).

## Monorepo development

Editable install from this directory:

```bash
cd src/praisonai-deploy
uv pip install -e .
```

Regression gates:

- `scripts/check_c14_deploy_imports.sh`
- `src/praisonai/tests/unit/test_c14_deploy_backward_compat.py`
- `src/praisonai-deploy/tests/`
