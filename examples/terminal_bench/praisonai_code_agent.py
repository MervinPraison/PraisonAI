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
    Harbor Container → `praisonai code "TASK" --dangerously-skip-approval` (headless)

Notes:
    - `--dangerously-skip-approval` sets PRAISON_APPROVAL_MODE=auto +
      PRAISONAI_TOOL_SAFETY=off so the assistant runs fully autonomously in the
      container (no approval hang in a non-TTY session).
    - `praisonai code` always exits 0; Harbor grades by task verification, so the
      process exit code is intentionally ignored.
    - The base `praisonai` package is sufficient; heavy `code` extras are not
      required (ACP tools degrade gracefully).

Dependencies:
    pip install harbor praisonai praisonaiagents
"""

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
            f"praisonai code {shlex.quote(instruction)} "
            f"--dangerously-skip-approval "
            f"--model {shlex.quote(model)} "
            "> /tmp/praisonai_code.log 2>&1; "
            # Tee the log into logs_dir so populate_context_post_run can read it.
            "cp /tmp/praisonai_code.log /tmp/praisonai_code_run.log 2>/dev/null || true; "
            # Ignore exit code: `praisonai code` always exits 0 and Harbor grades
            # by task verification.
            "true"
        )

        # `extra_env` is the --ae channel; merge it into the exec env (never host
        # os.environ). `env` on BaseInstalledAgent already includes extra_env.
        await self.exec_as_agent(
            environment,
            command=command,
            env=self.env,
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        """`praisonai code` exposes no machine-readable metrics headlessly.

        Record identifying metadata; token/cost accounting is not available from
        the CLI's mixed stdout, so we leave those fields unset rather than guess.
        """
        context.metadata = {
            "framework": "praisonai",
            "agent_type": "code-cli",
            "agent_name": self.name(),
            "model": self.model_name,
            "log_path": "/tmp/praisonai_code.log",
        }


if __name__ == "__main__":
    print("PraisonAI Code Agent for Terminal-Bench 2.1")
    print("Usage:")
    print("  harbor run -d terminal-bench/terminal-bench-2-1 \\")
    print('    --agent "examples.terminal_bench.praisonai_code_agent:PraisonAICodeAgent" \\')
    print("    -m openai/gpt-4o-mini --ae OPENAI_API_KEY=$OPENAI_API_KEY -n 4")
