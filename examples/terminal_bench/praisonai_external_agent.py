"""
PraisonAI External Agent for Terminal-Bench 2.0 (Harbor)

An external agent that bridges PraisonAI's Agent class with Harbor's
BaseEnvironment interface. The agent uses Harbor's exec() as a bash tool.

Usage:
    harbor run -d terminal-bench/terminal-bench-2 \
        --agent-import-path examples.terminal_bench.praisonai_external_agent:PraisonAIExternalAgent \
        --model openai/gpt-4o \
        --ae OPENAI_API_KEY=$OPENAI_API_KEY

Architecture:
    Harbor Container ←→ BaseEnvironment.exec() ←→ bash_tool ←→ PraisonAI Agent

Dependencies:
    pip install harbor praisonaiagents
"""

import os
from typing import Any

try:
    from harbor.agents.base import BaseAgent
    from harbor.environments.base import BaseEnvironment  
    from harbor.models.agent.context import AgentContext
except ImportError as e:
    raise ImportError(
        f"Harbor framework not installed: {e}\n"
        "Install with: pip install harbor"
    ) from e

try:
    from praisonaiagents import Agent
    from praisonaiagents.approval import get_approval_registry, AutoApproveBackend
except ImportError as e:
    raise ImportError(
        f"PraisonAI not installed: {e}\n"
        "Install with: pip install praisonaiagents"
    ) from e


class PraisonAIExternalAgent(BaseAgent):
    """External PraisonAI agent that drives a Harbor container environment."""

    @staticmethod
    def name() -> str:
        return "praisonai"

    def version(self) -> str | None:
        try:
            import praisonaiagents
            return (
                getattr(praisonaiagents, "__version__", None)
                or getattr(praisonaiagents, "version", None)
                or "unknown"
            )
        except ImportError:
            return None

    async def setup(self, environment: BaseEnvironment) -> None:
        """Setup phase - external agent needs no container setup."""
        pass

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """
        Run the PraisonAI agent on the given instruction using Harbor's environment.
        
        This method bridges Harbor's BaseEnvironment.exec() to PraisonAI's tool system.
        """
        
        # Inject API keys from Harbor's --ae env vars into host os.environ
        # so litellm can pick them up (--ae only sets them inside Docker, not the host)
        agent_env = getattr(context, 'env', {}) or {}
        for key, val in agent_env.items():
            if key not in os.environ and val:
                os.environ[key] = val
                print(f"[ENV] Set {key} from Harbor agent env")

        # Set auto-approval for container-isolated execution  
        # Harbor's container provides isolation, so we can safely auto-approve shell commands
        registry = get_approval_registry()
        original_backend = registry.get_backend()
        registry.set_backend(AutoApproveBackend(), agent_name="terminal-agent")
        
        try:
            # Create bash tool that wraps Harbor's environment.exec()
            async def bash_tool(command: str) -> str:
                """Execute a bash command in the Harbor sandboxed environment."""
                if not command.strip():
                    return "Error: Empty command provided"
                
                print(f"[CMD] {command[:200]}")
                try:
                    # Execute command in Harbor's container
                    result = await environment.exec(command=command, timeout_sec=300)
                    
                    # Format output similar to PraisonAI's execute_command tool
                    output_parts = []
                    if result.stdout:
                        output_parts.append(result.stdout.strip())
                    if result.stderr:
                        output_parts.append(f"[stderr]: {result.stderr.strip()}")
                    if result.return_code != 0:
                        output_parts.append(f"[exit_code]: {result.return_code}")
                        
                    output = "\n".join(output_parts) if output_parts else "(no output)"
                    print(f"[OUT] {output[:300]}")
                    return output
                    
                except Exception as e:
                    print(f"[ERR] {str(e)}")
                    return f"Error executing command: {str(e)}"

            # Create PraisonAI agent with the bash tool
            agent = Agent(
                name="terminal-agent",
                instructions=(
                    "You are an expert terminal agent. You solve coding, debugging, data analysis, security, "
                    "and system administration tasks using the bash_tool to run shell commands."
                    "\n\nCRITICAL RULES:"
                    "\n1. START by exploring: ls /app/ && cat /app/*.py /app/*.sh /app/*.txt 2>/dev/null | head -200"
                    "   Read ALL task files to understand what is needed before doing anything."
                    "\n2. Find and run the test IMMEDIATELY to see what is expected:"
                    "   find /app -name 'test_*.py' | head -3 && cd /app && python3 -m pytest -v 2>&1 | tail -40 || true"
                    "   The test error trace tells you EXACTLY what output/behavior is required."
                    "\n3. ITERATE: implement a solution, run the test, read the error, refine. Repeat until it passes."
                    "   Never give up after one attempt — try multiple approaches if needed."
                    "\n4. For writing files with special characters use Python:"
                    "   python3 -c \"with open('/app/file','w') as f: f.write('content')\""
                    "   or heredoc: cat > /app/file << 'EOF'\\n...content...\\nEOF"
                    "\n5. Read ALL error messages — they tell you exactly what to fix next."
                    "\n6. NEVER just describe your plan. ALWAYS immediately run bash_tool commands."
                    "   Keep calling bash_tool until the test PASSES or you have exhausted all approaches."
                ),
                tools=[bash_tool],
                llm=self.model_name or "openai/gpt-4o",
            )

            # Execute the agent with outer loop to handle premature stopping
            print(f"🚀 PraisonAI Agent starting task: {instruction[:100]}...")
            result = await agent.achat(instruction)
            for _iter in range(19):
                result_str = str(result)
                # Stop if test passed
                if any(sig in result_str.lower() for sig in [
                    " passed", "passed ", "test passed", "all tests pass", "1 passed"
                ]):
                    break
                result = await agent.achat(
                    "The task is NOT complete yet — keep working. Run bash_tool commands now. "
                    "If you haven't already: (1) read all files in /app/, "
                    "(2) run the test to see the exact failure, "
                    "(3) implement a fix, (4) run the test again. "
                    "Repeat until the test passes. What is your next bash_tool command?"
                )
            print(f"✅ PraisonAI Agent completed task")
            
            # Populate Harbor context with metadata
            self._populate_context(agent, context, result)
            
        except Exception as e:
            print(f"❌ PraisonAI Agent failed: {str(e)}")
            context.metadata = {"error": str(e)}
            raise
        finally:
            # Restore original approval backend to avoid global state pollution
            if original_backend:
                registry.set_backend(original_backend)
            else:
                registry.remove_backend(agent_name="terminal-agent")

    def _populate_context(self, agent: Agent, context: AgentContext, result: Any) -> None:
        """
        Populate Harbor's AgentContext with metrics from PraisonAI agent execution.
        
        Harbor tracks: n_input_tokens, n_output_tokens, cost_usd, metadata
        """
        try:
            # Extract token usage and cost from agent
            try:
                summary = agent.cost_summary() if callable(getattr(agent, 'cost_summary', None)) else None
                if isinstance(summary, dict):
                    context.n_input_tokens = summary.get('tokens_in')
                    context.n_output_tokens = summary.get('tokens_out')
                    context.cost_usd = summary.get('cost')
                else:
                    context.n_input_tokens = getattr(agent, '_total_tokens_in', 0)
                    context.n_output_tokens = getattr(agent, '_total_tokens_out', 0)
                    context.cost_usd = getattr(agent, 'total_cost', None)
            except Exception:
                pass
                
            # Store result summary and agent info
            context.metadata = {
                "agent_name": agent.name,
                "model": getattr(agent, 'llm', 'unknown'),
                "final_response": str(result)[:500] if result else None,
                "tools_used": ["bash_tool"],
                "framework": "praisonai",
                "version": self.version(),
            }
            
        except Exception as e:
            # Don't fail the whole run if context population fails
            context.metadata = {"context_error": str(e)}


# Example usage for testing
if __name__ == "__main__":
    print("PraisonAI External Agent for Terminal-Bench 2.0")
    print("Usage: harbor run -d terminal-bench/terminal-bench-2 \\")
    print("  --agent-import-path examples.terminal_bench.praisonai_external_agent:PraisonAIExternalAgent \\")
    print("  --model openai/gpt-4o")
    print()
    print("Dependencies:")
    print("  pip install harbor praisonaiagents")