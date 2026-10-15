# Standalone OpenShell image for the PraisonAI contract risk review example.
#   docker build -t praisonai-contract-review:dev .
# OpenShell does not run the image CMD; the command goes after `--` on
# `openshell sandbox create`.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

# Must be a release that includes the YAML CLI fixes from
# MervinPraison/PraisonAI#5826 (--metrics-json PATH, output_file, exit code).
ARG PRAISONAI_VERSION=4.7.14
# Only needed when the image is used with `nemoclaw onboard --from`.
ARG NEMOCLAW_TOOL_DISCLOSURE=progressive
ENV NEMOCLAW_TOOL_DISCLOSURE=${NEMOCLAW_TOOL_DISCLOSURE}

RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir "praisonai==${PRAISONAI_VERSION}"

# The canary is owned by `sandbox`, so file permissions allow the write and only
# the policy's read-only /etc can block it (see probes/sandbox_probe.py).
RUN groupadd -g 1000 sandbox \
 && useradd -m -d /sandbox -u 1000 -g sandbox -s /bin/bash sandbox \
 && install -o sandbox -g sandbox -m 0644 /dev/null /etc/praisonai-canary

# Root-owned and read-only to the agent; run.sh copies it to /sandbox/work.
COPY app/ /app/

# OPENAI_API_KEY is a placeholder: OpenShell injects the real credential at the
# proxy, but PraisonAI rejects an empty key. The remaining variables switch off
# telemetry, update checks and LiteLLM's cost-map download from GitHub.
ENV PATH=/opt/venv/bin:$PATH \
    HOME=/sandbox \
    OPENAI_BASE_URL=https://inference.local/v1 \
    OPENAI_API_KEY=openshell-managed-inference \
    PRAISONAI_TELEMETRY_DISABLED=true \
    DO_NOT_TRACK=true \
    PRAISONAI_NO_UPDATE_CHECK=1 \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    PRAISONAI_ALLOW_LOCAL_TOOLS=true

WORKDIR /sandbox
USER sandbox
CMD ["/bin/bash"]
