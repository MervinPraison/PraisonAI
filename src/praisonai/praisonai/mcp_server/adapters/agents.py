"""
Agents Adapter

Maps PraisonAI agent operations to MCP tools.
"""

import logging
from typing import Optional

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_agent_tools() -> None:
    """Register agent-related MCP tools."""
    
    @register_tool("praisonai.agent.chat")
    def agent_chat(
        message: str,
        model: str = "gpt-4o-mini",
        instructions: Optional[str] = None,
    ) -> str:
        """Chat with a PraisonAI agent."""
        try:
            from praisonaiagents import Agent
            
            agent = Agent(
                instructions=instructions or "You are a helpful assistant.",
                llm=model,
            )
            result = agent.chat(message)
            return str(result)
        except ImportError:
            return "Error: praisonaiagents not installed"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.agent.run")
    def agent_run(
        task: str,
        model: str = "gpt-4o-mini",
        instructions: Optional[str] = None,
    ) -> str:
        """Run a task with a PraisonAI agent."""
        try:
            from praisonaiagents import Agent
            
            agent = Agent(
                instructions=instructions or "You are a helpful assistant.",
                llm=model,
            )
            result = agent.start(task)
            return str(result)
        except ImportError:
            return "Error: praisonaiagents not installed"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.workflow.run")
    def workflow_run(
        yaml_content: str,
    ) -> str:
        """Run a workflow from YAML definition."""
        try:
            import yaml
            from praisonai.agents_generator import AgentsGenerator
            
            # Parse YAML to validate
            yaml.safe_load(yaml_content)
            
            # Write to temp file and run
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(yaml_content)
                temp_path = f.name
            
            generator = AgentsGenerator(
                agent_file=temp_path,
                framework="praisonai",
            )
            result = generator.generate_crew_and_kickoff()
            return str(result)
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.workflow.run_file")
    def workflow_run_file(
        file_path: str,
    ) -> str:
        """Run a workflow from YAML file path."""
        try:
            from praisonai.agents_generator import AgentsGenerator
            
            generator = AgentsGenerator(
                agent_file=file_path,
                framework="praisonai",
            )
            result = generator.generate_crew_and_kickoff()
            return str(result)
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.research.run")
    def research_run(
        topic: str,
        depth: str = "medium",
    ) -> str:
        """Run deep research on a topic."""
        try:
            from praisonaiagents import Agent
            
            instructions = f"""You are a research agent. Conduct thorough research on the given topic.
            Research depth: {depth}
            Provide comprehensive findings with sources where possible."""
            
            agent = Agent(
                instructions=instructions,
                llm="gpt-4o",
            )
            result = agent.start(f"Research the following topic thoroughly: {topic}")
            return str(result)
        except ImportError:
            return "Error: praisonaiagents not installed"
        except Exception as e:
            return f"Error: {e}"
    
    logger.info("Registered agent MCP tools")
