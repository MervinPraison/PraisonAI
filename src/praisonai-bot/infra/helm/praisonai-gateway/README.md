# praisonai-gateway Helm chart

Minimal, production-oriented Helm chart for the PraisonAI **gateway** (WebSocket +
REST) service. It reuses the official GHCR image — no new build pipeline is required.

## Quick start

```bash
# 1. Create the auth secret (recommended over inline tokens)
kubectl create secret generic praisonai-gateway-auth \
  --from-literal=GATEWAY_AUTH_TOKEN="$(openssl rand -hex 16)"

# 2. Install from a local checkout
helm install praisonai ./src/praisonai-bot/infra/helm/praisonai-gateway \
  --set auth.existingSecret=praisonai-gateway-auth \
  --set image.tag=latest
```

Port-forward to test:

```bash
kubectl port-forward svc/praisonai-praisonai-gateway 8765:8765
curl http://127.0.0.1:8765/health
```

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `replicaCount` | `1` | Gateway replicas. See WebSocket note below before scaling. |
| `image.repository` | `ghcr.io/mervinpraison/praisonai` | Official GHCR image. |
| `image.tag` | `""` (Chart `appVersion`) | Pin a released tag in production. |
| `command` | `["praisonai","gateway","start","--host","0.0.0.0"]` | Container entrypoint. |
| `auth.enabled` | `true` | Inject `GATEWAY_AUTH_TOKEN` into the pod. |
| `auth.existingSecret` | `""` | Reference a pre-created Secret (preferred / GitOps-friendly). |
| `auth.token` | `""` | Inline token; chart creates a Secret. Avoid in Git. |
| `service.port` | `8765` | Gateway listen port (`GATEWAY_PORT`). |
| `ingress.enabled` | `false` | Expose via Ingress with WebSocket annotations. |
| `probes.path` | `/health` | Liveness/readiness probe path. |
| `autoscaling.enabled` | `false` | Optional CPU-based HPA. |

See [`values.yaml`](./values.yaml) for the full list, including `env` (e.g.
`OPENAI_API_KEY` via `secretKeyRef`), ingress hosts/TLS, resources, and scheduling.

## Security

When `auth.enabled=true` (the default) the chart **refuses to render** unless a
token source (`auth.existingSecret` or `auth.token`) is provided — otherwise the
pod would reference a Secret that is never created. If the gateway is additionally
exposed via `ingress.enabled=true`, the failure message calls out the security
risk explicitly, so you cannot accidentally expose an unauthenticated gateway.

To run without a token (e.g. local testing behind trusted networking) set
`auth.enabled=false`.

## WebSocket ingress

The gateway is stateful per connection. The default NGINX annotations set long
read/send timeouts. For multiple replicas, enable **sticky sessions** (or a shared
session backend) — otherwise reconnecting clients may land on a different pod:

```yaml
ingress:
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    nginx.ingress.kubernetes.io/affinity: "cookie"
```

## Scope

This chart intentionally covers the **gateway** only. Other services (serve, claw,
bots) run from their own GHCR images and can be templated similarly if needed.
