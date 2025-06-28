"""
Advanced Dynamic Input Example for PraisonAI

This example demonstrates an advanced system that dynamically creates agents and tasks
based on user inputs, including conditional logic, custom configurations, and file output.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo
import os
from typing import Dict, List

class DynamicAgentSystem:
    """Advanced system for handling dynamic user inputs"""
    
    def __init__(self):
        self.user_preferences = {}
        self.llm_config = {
            "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
            "temperature": 0.7
        }
    
    def collect_user_inputs(self) -> Dict[str, str]:
        """Collect multiple user inputs"""
        inputs = {}
        inputs['topic'] = input("What topic would you like to explore? ")
        inputs['depth'] = input("Analysis depth (quick/detailed)? ").lower() or "quick"
        inputs['output_format'] = input("Output format (summary/report/bullets)? ").lower() or "summary"
        inputs['language'] = input("Language preference (en/es/fr)? ").lower() or "en"
        return inputs
    
    def create_dynamic_agents(self, inputs: Dict[str, str]) -> List[Agent]:
        """Create agents based on user inputs"""
        agents = []
        
        # Research agent with dynamic configuration
        research_agent = Agent(
            name="ResearchExpert",
            role=f"{'Detailed' if inputs['depth'] == 'detailed' else 'Quick'} Research Specialist",
            goal=f"Conduct {inputs['depth']} research on {inputs['topic']} in {inputs['language']}",
            backstory=f"Multilingual expert specializing in {inputs['depth']} analysis",
            tools=[duckduckgo],
            self_reflect=inputs['depth'] == 'detailed',
            llm=self.llm_config
        )
        agents.append(research_agent)
        
        # Format agent based on output preference
        format_agent = Agent(
            name="FormatExpert",
            role=f"{inputs['output_format'].title()} Formatter",
            goal=f"Format research into {inputs['output_format']} style",
            backstory=f"Expert in creating {inputs['output_format']} documents",
            llm=self.llm_config
        )
        agents.append(format_agent)
        
        # Optional quality agent for detailed analysis
        if inputs['depth'] == 'detailed':
            quality_agent = Agent(
                name="QualityChecker",
                role="Quality Assurance Specialist",
                goal="Verify accuracy and completeness",
                backstory="Expert in fact-checking and quality control",
                llm=self.llm_config
            )
            agents.append(quality_agent)
        
        return agents
    
    def create_dynamic_tasks(self, agents: List[Agent], inputs: Dict[str, str]) -> List[Task]:
        """Create tasks based on user inputs and agents"""
        tasks = []
        
        # Research task
        research_task = Task(
            description=f"""
            Research '{inputs['topic']}' with the following requirements:
            - Depth: {inputs['depth']}
            - Language: {inputs['language']}
            - Find {'5-10' if inputs['depth'] == 'detailed' else '3-5'} key points
            - Include sources and citations
            """,
            expected_output=f"Research findings about {inputs['topic']} with sources",
            agent=agents[0],  # Research agent
            name="research_phase"
        )
        tasks.append(research_task)
        
        # Formatting task
        format_instructions = {
            'summary': "Create a concise paragraph summary",
            'report': "Create a structured report with sections",
            'bullets': "Create a bullet-point list of key findings"
        }
        
        format_task = Task(
            description=f"""
            Format the research findings as follows:
            - Style: {format_instructions[inputs['output_format']]}
            - Language: {inputs['language']}
            - Maintain all source citations
            """,
            expected_output=f"{inputs['output_format'].title()} of {inputs['topic']}",
            agent=agents[1],  # Format agent
            context=[research_task],
            name="formatting_phase"
        )
        tasks.append(format_task)
        
        # Quality check task (if detailed)
        if inputs['depth'] == 'detailed' and len(agents) > 2:
            quality_task = Task(
                description="Verify all facts, check sources, and ensure completeness",
                expected_output="Quality-assured final output with verification notes",
                agent=agents[2],  # Quality agent
                context=[format_task],
                name="quality_phase"
            )
            tasks.append(quality_task)
        
        return tasks
    
    def run(self):
        """Main execution flow"""
        # Collect inputs
        print("🎯 PraisonAI Dynamic Input System")
        print("-" * 40)
        inputs = self.collect_user_inputs()
        
        # Create dynamic agents and tasks
        agents = self.create_dynamic_agents(inputs)
        tasks = self.create_dynamic_tasks(agents, inputs)
        
        # Configure process based on depth
        process = "hierarchical" if inputs['depth'] == 'detailed' else "sequential"
        
        # Run the system
        print(f"\n🚀 Starting {process} analysis for '{inputs['topic']}'...")
        praison_agents = PraisonAIAgents(
            agents=agents,
            tasks=tasks,
            process=process,
            verbose=inputs['depth'] == 'detailed'
        )
        
        result = praison_agents.start()
        
        # Save results if detailed
        if inputs['depth'] == 'detailed':
            filename = f"{inputs['topic'].replace(' ', '_')}_{inputs['output_format']}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(result)
            print(f"\n📄 Results saved to: {filename}")
        
        return result

# Usage
if __name__ == "__main__":
    system = DynamicAgentSystem()
    result = system.run()
    print("\n📊 Final Result:")
    print(result)