"""
Multi-Agent PraisonAI Integration for Terminal-Bench 2.0

This example shows how to use PraisonAI's AgentTeam and AgentFlow
capabilities with Terminal-Bench 2.0 for complex multi-step tasks.

The multi-agent approach is useful for Terminal-Bench tasks that benefit from:
- Task planning and decomposition
- Specialized roles (planner, executor, verifier)
- Error correction and refinement
- Complex workflows with multiple phases

Usage:
    harbor run -d terminal-bench/terminal-bench-2 \
        --agent-import-path examples.terminal_bench.multi_agent_example:MultiAgentPraisonAI \
        --model openai/gpt-4o
"""

import asyncio
from typing import Any, Dict, Optional

try:
    from harbor.agents.base import BaseAgent
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext
except ImportError as e:
    raise ImportError(f"Harbor framework required: {e}") from e

try:
    from praisonaiagents import Agent, AgentTeam, Task
    from praisonaiagents.approval import get_approval_registry, AutoApproveBackend
except ImportError as e:
    raise ImportError(f"PraisonAI required: {e}") from e


class MultiAgentPraisonAI(BaseAgent):
    """Multi-agent PraisonAI system for complex Terminal-Bench tasks."""
    
    @staticmethod
    def name() -> str:
        return "praisonai-multi"

    def version(self) -> str | None:
        try:
            import praisonaiagents
            return getattr(praisonaiagents, "__version__", None)
        except ImportError:
            return None

    async def setup(self, environment: BaseEnvironment) -> None:
        """Setup phase - no container setup needed for external agent."""
        pass

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """
        Run multi-agent PraisonAI team on the Terminal-Bench task.
        
        Uses a three-agent approach:
        1. Planner: Analyzes task and creates execution plan
        2. Executor: Implements the plan using shell commands  
        3. Verifier: Tests and validates the solution
        """
        
        # Set auto-approval for container safety
        registry = get_approval_registry()
        original_backend = registry.get_backend()
        registry.set_backend(AutoApproveBackend(), agent_name="multi-agent-planner")
        
        try:
            # Create bash tool that wraps Harbor environment
            async def bash_tool(command: str) -> str:
                """Execute bash command in Harbor environment."""
                if not command.strip():
                    return "Error: Empty command"
                    
                try:
                    result = await environment.exec(command=command, timeout_sec=30)
                    output_parts = []
                    if result.stdout:
                        output_parts.append(result.stdout.strip())
                    if result.stderr:
                        output_parts.append(f"[stderr]: {result.stderr.strip()}")
                    if result.return_code != 0:
                        output_parts.append(f"[exit_code]: {result.return_code}")
                    return "\n".join(output_parts) if output_parts else "(no output)"
                except Exception as e:
                    return f"Error: {str(e)}"

            # Create specialized agents
            planner = Agent(
                name="planner",
                instructions=(
                    "You are an expert task planner for terminal/coding tasks. "
                    "Analyze the given instruction and create a detailed, step-by-step plan. "
                    "Break down complex tasks into smaller, manageable steps. "
                    "Consider potential issues and edge cases. "
                    "Output your plan as a numbered list of specific actions."
                ),
                llm=self.model_name or "openai/gpt-4o",
                verbose=False,
            )
            
            executor = Agent(
                name="executor", 
                instructions=(
                    "You are an expert terminal executor. "
                    "Follow the provided plan step-by-step using bash commands. "
                    "Use the bash_tool to execute commands safely. "
                    "Be precise and check each step before proceeding. "
                    "If a step fails, try alternative approaches."
                ),
                tools=[bash_tool],
                llm=self.model_name or "openai/gpt-4o", 
                verbose=False,
            )
            
            verifier = Agent(
                name="verifier",
                instructions=(
                    "You are a solution verifier and tester. "
                    "Test the completed solution to ensure it works correctly. "
                    "Run appropriate tests and checks using bash commands. "
                    "Report whether the solution meets the requirements. "
                    "If issues are found, suggest specific fixes."
                ),
                tools=[bash_tool],
                llm=self.model_name or "openai/gpt-4o",
                verbose=False,
            )

            print(f"🚀 Multi-Agent PraisonAI starting: {instruction[:100]}...")
            
            # Phase 1: Planning
            print("📋 Phase 1: Task Planning")
            plan = await planner.astart(f"Create a detailed plan for: {instruction}")
            print(f"Plan created: {len(plan.split('.')) if plan else 0} steps")
            
            # Phase 2: Execution
            print("⚡ Phase 2: Task Execution") 
            execution_prompt = f"Execute this plan step by step:\n\nOriginal task: {instruction}\n\nPlan:\n{plan}"
            execution_result = await executor.astart(execution_prompt)
            print("Execution completed")
            
            # Phase 3: Verification
            print("✅ Phase 3: Solution Verification")
            verification_prompt = f"Verify this solution works correctly:\n\nOriginal task: {instruction}\n\nSolution: {execution_result}\n\nRun tests to confirm it works."
            verification_result = await verifier.astart(verification_prompt)
            print("Verification completed")
            
            # Combine results
            final_result = {
                "plan": plan,
                "execution": execution_result,
                "verification": verification_result,
            }
            
            print("✅ Multi-Agent PraisonAI completed task")
            
            # Populate context
            self._populate_context([planner, executor, verifier], context, final_result)
            
        except Exception as e:
            print(f"❌ Multi-Agent PraisonAI failed: {str(e)}")
            context.metadata = {"error": str(e)}
            raise
        finally:
            # Restore original approval backend to avoid global state pollution
            if original_backend:
                registry.set_backend(original_backend)
            else:
                registry.remove_backend(agent_name="multi-agent-planner")

    def _populate_context(self, agents: list, context: AgentContext, result: Dict[str, Any]) -> None:
        """Populate Harbor context with multi-agent metrics."""
        try:
            # Aggregate token usage from all agents
            total_input_tokens = 0
            total_output_tokens = 0
            total_cost = 0.0
            
            for agent in agents:
                # Use agent's actual metrics properties
                total_input_tokens += getattr(agent, '_total_tokens_in', 0)
                total_output_tokens += getattr(agent, '_total_tokens_out', 0)
                total_cost += agent.total_cost or 0.0
            
            context.n_input_tokens = total_input_tokens if total_input_tokens > 0 else None
            context.n_output_tokens = total_output_tokens if total_output_tokens > 0 else None
            context.cost_usd = total_cost if total_cost > 0 else None
            
            context.metadata = {
                "framework": "praisonai-multi",
                "agent_type": "multi-agent-team", 
                "agents": [agent.name for agent in agents],
                "model": self.model_name or "openai/gpt-4o",
                "phases": ["planning", "execution", "verification"],
                "tools_used": ["bash_tool"],
                "result_summary": str(result.get("verification", ""))[:200],
                "version": self.version(),
            }
            
        except Exception as e:
            context.metadata = {"context_error": str(e)}


# Alternative implementation using AgentTeam (more structured)
class AgentTeamPraisonAI(BaseAgent):
    """AgentTeam-based implementation for Terminal-Bench tasks."""
    
    @staticmethod
    def name() -> str:
        return "praisonai-team"
        
    def version(self) -> str | None:
        try:
            import praisonaiagents
            return getattr(praisonaiagents, "__version__", None)
        except ImportError:
            return None

    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    async def run(
        self, 
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run structured AgentTeam workflow."""
        
        registry = get_approval_registry()
        original_backend = registry.get_backend()
        registry.set_backend(AutoApproveBackend(), agent_name="agent-team")
        
        try:
            # Create bash tool
            async def bash_tool(command: str) -> str:
                result = await environment.exec(command=command, timeout_sec=30)
                output_parts = []
                if result.stdout:
                    output_parts.append(result.stdout.strip())
                if result.stderr:
                    output_parts.append(f"[stderr]: {result.stderr.strip()}")
                if result.return_code != 0:
                    output_parts.append(f"[exit_code]: {result.return_code}")
                return "\n".join(output_parts) if output_parts else "(no output)"

            # Create agents
            planner = Agent(
                name="planner",
                instructions="Create detailed execution plans for terminal tasks",
                llm=self.model_name or "openai/gpt-4o"
            )
            
            executor = Agent(
                name="executor",
                instructions="Execute terminal commands based on plans",
                tools=[bash_tool],
                llm=self.model_name or "openai/gpt-4o"
            )
            
            # Create tasks
            plan_task = Task(
                name="plan",
                description=f"Create plan for: {instruction}",
                agent=planner
            )
            
            execute_task = Task(
                name="execute", 
                description=f"Execute plan for: {instruction}",
                agent=executor,
                dependencies=[plan_task]  # Execute after planning
            )
            
            # Create and run team
            team = AgentTeam(
                agents=[planner, executor],
                tasks=[plan_task, execute_task],
                process="sequential"
            )
            
            print(f"🚀 AgentTeam starting: {instruction[:100]}...")
            result = await team.astart(instruction)
            print("✅ AgentTeam completed")
            
            # Populate context
            context.metadata = {
                "framework": "praisonai-team",
                "workflow": "sequential",
                "agents_count": len(team.agents),
                "tasks_count": len(team.tasks),
                "result": str(result)[:200] if result else None,
            }
            
        finally:
            # Restore original approval backend to avoid global state pollution
            if original_backend:
                registry.set_backend(original_backend)
            else:
                registry.remove_backend(agent_name="agent-team")


if __name__ == "__main__":
    print("Multi-Agent PraisonAI for Terminal-Bench 2.0")
    print("=" * 50)
    print()
    print("Available agent implementations:")
    print("1. MultiAgentPraisonAI - Custom multi-agent workflow")
    print("2. AgentTeamPraisonAI - Structured AgentTeam workflow")
    print()
    print("Usage examples:")
    print()
    print("# Multi-agent custom workflow")
    print("harbor run -d terminal-bench/terminal-bench-2 \\")
    print("  --agent-import-path examples.terminal_bench.multi_agent_example:MultiAgentPraisonAI \\")
    print("  --model openai/gpt-4o")
    print()
    print("# AgentTeam structured workflow")  
    print("harbor run -d terminal-bench/terminal-bench-2 \\")
    print("  --agent-import-path examples.terminal_bench.multi_agent_example:AgentTeamPraisonAI \\")
    print("  --model openai/gpt-4o")
    print()
    print("Benefits of multi-agent approach:")
    print("- Task decomposition and planning")
    print("- Specialized roles and expertise")
    print("- Error detection and correction")
    print("- Higher success rates on complex tasks")