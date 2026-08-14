# praisonai: skip=true
"""
PraisonAI Code Agent for Terminal-Bench 2.1 (Harbor)

The headline adapter: benchmarks the terminal-native `praisonai code` assistant
by installing it inside the Harbor container and driving it headlessly.

Usage:
    harbor run -d terminal-bench/terminal-bench-2-1 \
        --agent "examples.terminal_bench.praisonai_code_agent:PraisonAICodeAgent" \
        -m openai/gpt-4o-mini \
        --ae OPENAI_API_KEY=$OPENAI_API_KEY \
        -n 4

Architecture:
    Harbor Container → `praisonai code -p --output json "TASK" --dangerously-skip-approval`

Notes:
    - `--dangerously-skip-approval` sets PRAISON_APPROVAL_MODE=auto +
      PRAISONAI_TOOL_SAFETY=off so the assistant runs fully autonomously in the
      container (no approval hang in a non-TTY session).
    - The JSON envelope provides token, cost, session, and status metadata while
      the real exit status still surfaces install/auth/startup failures.
    - The base `praisonai` package is sufficient; heavy `code` extras are not
      required (ACP tools degrade gracefully).

Dependencies:
    pip install harbor praisonai praisonaiagents
"""

import json
import shlex

try:
    from harbor.agents.installed.base import BaseInstalledAgent
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext
except ImportError as e:  # pragma: no cover - only importable when Harbor present
    raise ImportError(
        f"Harbor framework not installed: {e}\n"
        "Install with: pip install harbor"
    ) from e


class PraisonAICodeAgent(BaseInstalledAgent):
    """Benchmarks the `praisonai code` terminal assistant inside a Harbor container."""

    @staticmethod
    def name() -> str:
        return "praisonai-code"

    def get_version_command(self) -> str:
        return "praisonai --version"

    async def install(self, environment: BaseEnvironment) -> None:
        """Install python + the praisonai CLI inside the container."""
        # System packages (best-effort; image may already have them).
        await self.exec_as_root(
            environment,
            command="apt-get update && apt-get install -y python3 python3-pip || true",
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )

        # PEP 668-safe install on bookworm-based images.
        version_spec = f"=={self._version}" if getattr(self, "_version", None) else ""
        await self.exec_as_agent(
            environment,
            command=(
                f"pip install --break-system-packages praisonai{version_spec} "
                "praisonaiagents"
            ),
        )

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Drive `praisonai code` headlessly on the instruction."""
        model = self.model_name or "openai/gpt-4o-mini"

        command = (
            f"praisonai code -p --output json {shlex.quote(instruction)} "
            f"--dangerously-skip-approval "
            f"--model {shlex.quote(model)} "
            "> /tmp/praisonai_code.log 2>&1; "
            # Capture the real exit status so install/auth/startup failures still
            # surface instead of being silently masked (Harbor otherwise records a
            # completed attempt for a crashed agent).
            "status=$?; "
            # Echo the envelope so Harbor captures it for post-run accounting.
            "cp /tmp/praisonai_code.log /tmp/praisonai_code_run.log 2>/dev/null || true; "
            "cat /tmp/praisonai_code.log; "
            # `praisonai code` normally exits 0 (Harbor grades by task
            # verification), so a genuine benchmark miss won't fail here — but a
            # nonzero status means the assistant itself failed to run.
            "exit $status"
        )

        # `--ae` / job YAML env vars arrive via BaseAgent.extra_env and are wired
        # into the container exec context by Harbor Trial, so no per-exec `env=`
        # is needed here.
        result = await self.exec_as_agent(
            environment,
            command=command,
        )
        self._last_stdout = getattr(result, "stdout", "") or ""

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Parse the headless JSON envelope into Harbor's accounting fields."""
        envelope = None
        for line in reversed(getattr(self, "_last_stdout", "").splitlines()):
            try:
                candidate = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(candidate, dict) and "status" in candidate:
                envelope = candidate
                break

        usage = envelope.get("usage", {}) if envelope else {}
        context.n_input_tokens = usage.get("in")
        context.n_output_tokens = usage.get("out")
        context.cost_usd = usage.get("cost")
        context.metadata = {
            "framework": "praisonai",
            "agent_type": "code-cli",
            "agent_name": self.name(),
            "model": self.model_name,
            "log_path": "/tmp/praisonai_code.log",
            "session_id": envelope.get("session_id") if envelope else None,
            "status": envelope.get("status") if envelope else "unknown",
        }


if __name__ == "__main__":
    print("PraisonAI Code Agent for Terminal-Bench 2.1")
    print("Usage:")
    print("  harbor run -d terminal-bench/terminal-bench-2-1 \\")
    print('    --agent "examples.terminal_bench.praisonai_code_agent:PraisonAICodeAgent" \\')
    print("    -m openai/gpt-4o-mini --ae OPENAI_API_KEY=$OPENAI_API_KEY -n 4")
