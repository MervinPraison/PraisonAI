"""
Named Toolsets Example

This example demonstrates how to use named toolsets to organize and reuse 
groups of tools across agents and workflows.

Toolsets provide:
- Organized tool collections (web, research, development, etc.)
- Progressive disclosure (safe → research → development)
- Composable design (toolsets can include other toolsets)
- YAML configuration support
"""

import os
from praisonaiagents import Agent, Task, AgentTeam
from praisonaiagents.toolsets import (
    list_toolsets, 
    resolve_toolset,
    register_toolset
)

# Set up environment (replace with your actual API key)
os.environ.setdefault("OPENAI_API_KEY", "your-openai-api-key-here")


def demo_basic_toolsets():
    """Demonstrate basic toolset functionality."""
    print("=== Basic Toolsets Demo ===")
    
    # List available toolsets
    available_toolsets = list_toolsets()
    print(f"Available toolsets: {available_toolsets}")
    
    # Show what tools are in each prebuilt toolset
    for toolset_name in ["safe", "web", "research"]:
        tools = resolve_toolset(toolset_name)
        print(f"\n{toolset_name.upper()} toolset contains: {tools}")


def demo_agent_with_toolsets():
    """Demonstrate agents using toolsets."""
    print("\n=== Agent with Toolsets Demo ===")
    
    # Create a research agent with research toolset
    researcher = Agent(
        name="researcher",
        role="Research Specialist",
        goal="Research topics thoroughly using web tools",
        instructions="You are a research specialist with access to web search and file tools.",
        toolsets=["research"],  # includes web tools + file tools
        llm="gpt-4o-mini"
    )
    
    print(f"Research agent has {len(researcher.tools)} tools available")
    print(f"Tools: {[getattr(t, '__name__', str(t)) for t in researcher.tools]}")
    
    # Create a safe agent with minimal tools
    safe_agent = Agent(
        name="safe_assistant",
        role="Safe Assistant", 
        goal="Help users safely without risky operations",
        instructions="You are a helpful assistant with access to only safe, read-only tools.",
        toolsets=["safe"],
        llm="gpt-4o-mini"
    )
    
    print(f"\nSafe agent has {len(safe_agent.tools)} tools available")
    print(f"Safe tools: {[getattr(t, '__name__', str(t)) for t in safe_agent.tools]}")


def demo_custom_toolsets():
    """Demonstrate creating and using custom toolsets."""
    print("\n=== Custom Toolsets Demo ===")
    
    # Register a custom toolset for data analysis
    register_toolset(
        "data_analysis",
        tools=["read_file", "write_file"],
        includes=["safe"],  # Include safe tools too
        description="Tools for data analysis workflows"
    )
    
    # Create an agent with the custom toolset
    analyst = Agent(
        name="data_analyst",
        role="Data Analyst",
        goal="Analyze data files and generate reports",
        instructions="You specialize in data analysis. Read files, process data, and write reports.",
        toolsets=["data_analysis"],
        llm="gpt-4o-mini"
    )
    
    print(f"Data analyst has {len(analyst.tools)} tools available")
    print(f"Analysis tools: {[getattr(t, '__name__', str(t)) for t in analyst.tools]}")


def demo_mixed_tools_and_toolsets():
    """Demonstrate mixing explicit tools with toolsets."""
    print("\n=== Mixed Tools and Toolsets Demo ===")
    
    # Create agent with both explicit tools and toolsets
    hybrid_agent = Agent(
        name="hybrid_assistant",
        role="Hybrid Assistant",
        goal="Assist with both research and custom tasks",
        instructions="You can research topics and perform custom analysis tasks.",
        tools=["write_file"],  # Explicit tool
        toolsets=["research"],  # Toolset with web + file tools
        llm="gpt-4o-mini"
    )
    
    print(f"Hybrid agent has {len(hybrid_agent.tools)} tools available")
    tool_names = [getattr(t, '__name__', str(t)) for t in hybrid_agent.tools]
    print(f"Hybrid tools: {tool_names}")
    
    # Note: write_file might appear twice (once explicit, once from toolset)
    # The agent handles deduplication automatically


def demo_multi_agent_with_toolsets():
    """Demonstrate multi-agent workflows with different toolsets."""
    print("\n=== Multi-Agent with Toolsets Demo ===")
    
    # Create agents with different toolsets for different roles
    researcher = Agent(
        name="researcher",
        role="Research Specialist",
        goal="Research topics and gather information",
        toolsets=["research"],
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="writer",
        role="Content Writer",  
        goal="Write content based on research",
        toolsets=["safe"],  # Safe tools for writing
        llm="gpt-4o-mini"
    )
    
    # Create tasks for each agent
    research_task = Task(
        name="research_task",
        description="Research the benefits of renewable energy",
        expected_output="A summary of key benefits of renewable energy",
        agent=researcher
    )
    
    writing_task = Task(
        name="writing_task", 
        description="Write a blog post about renewable energy based on the research",
        expected_output="A well-written blog post about renewable energy benefits",
        agent=writer
    )
    
    # Create team with different toolsets per agent
    team = AgentTeam(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        process="sequential"
    )
    
    print(f"Team created with {len(team.agents)} agents using different toolsets")
    print(f"Research agent tools: {len(researcher.tools)}")
    print(f"Writer agent tools: {len(writer.tools)}")


def demo_yaml_config():
    """Show how toolsets work in YAML configuration."""
    print("\n=== YAML Configuration Example ===")
    
    yaml_config = """
# agents.yaml - Example using toolsets
agents:
  researcher:
    role: Research Specialist
    goal: Research topics thoroughly
    toolsets:
      - research  # Includes web search, file tools
    llm: gpt-4o-mini
    
  analyst:
    role: Data Analyst
    goal: Analyze research data
    tools:
      - write_file  # Explicit tool
    toolsets:
      - safe  # Safe toolset
    llm: gpt-4o-mini

tasks:
  research_task:
    description: Research renewable energy trends
    agent: researcher
    expected_output: Research summary
    
  analysis_task:
    description: Analyze the research data
    agent: analyst
    expected_output: Analysis report
"""
    
    print("Example YAML configuration with toolsets:")
    print(yaml_config)
    print("Use: praisonai run 'Research renewable energy' --toolset research")
    print("Or:  praisonai chat --toolset web,files")


if __name__ == "__main__":
    print("🛠️  PraisonAI Named Toolsets Example")
    print("=" * 50)
    
    # Run all demos
    demo_basic_toolsets()
    demo_agent_with_toolsets()
    demo_custom_toolsets()
    demo_mixed_tools_and_toolsets()
    demo_multi_agent_with_toolsets()
    demo_yaml_config()
    
    print("\n✅ Toolsets example completed!")
    print("\n💡 Key Benefits:")
    print("   • Organized tool collections")
    print("   • Progressive disclosure (safe → research → development)")
    print("   • Reusable across agents and workflows") 
    print("   • YAML configuration support")
    print("   • Composable design with includes")