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

import asyncio
from typing import Any, Dict, Optional
from pathlib import Path

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
            return getattr(praisonaiagents, "__version__", None)
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
                
                try:
                    # Execute command in Harbor's container
                    result = await environment.exec(command=command, timeout_sec=30)
                    
                    # Format output similar to PraisonAI's execute_command tool
                    output_parts = []
                    if result.stdout:
                        output_parts.append(result.stdout.strip())
                    if result.stderr:
                        output_parts.append(f"[stderr]: {result.stderr.strip()}")
                    if result.return_code != 0:
                        output_parts.append(f"[exit_code]: {result.return_code}")
                        
                    return "\n".join(output_parts) if output_parts else "(no output)"
                    
                except Exception as e:
                    return f"Error executing command: {str(e)}"

            # Create PraisonAI agent with the bash tool
            agent = Agent(
                name="terminal-agent",
                instructions=(
                    "You are an expert terminal agent working on coding and system administration tasks. "
                    "Use the bash_tool to execute shell commands in the sandboxed environment. "
                    "Be precise, verify your work, and complete the task step by step. "
                    "Always check if your solution works by running appropriate tests."
                ),
                tools=[bash_tool],
                llm=self.model_name or "openai/gpt-4o",
            )

            # Execute the agent
            print(f"🚀 PraisonAI Agent starting task: {instruction[:100]}...")
            result = await agent.astart(instruction)
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
            summary = agent.cost_summary()
            if summary:
                context.n_input_tokens = summary.get('tokens_in')
                context.n_output_tokens = summary.get('tokens_out')
                context.cost_usd = summary.get('cost')
            else:
                # Fallback to direct properties
                context.n_input_tokens = getattr(agent, '_total_tokens_in', 0)
                context.n_output_tokens = getattr(agent, '_total_tokens_out', 0) 
                context.cost_usd = agent.total_cost
                
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