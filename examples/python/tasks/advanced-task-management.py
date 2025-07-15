"""
Advanced Task Management Example

This example demonstrates sophisticated task management including conditional execution,
validation feedback loops, dynamic task routing, and complex task dependencies.

Features demonstrated:
- Conditional task execution based on results
- Validation feedback loops with retry mechanisms  
- Dynamic task routing and decision trees
- Complex task dependencies and context passing
- Quality assurance workflows
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.task import TaskOutput
from praisonaiagents.tools import duckduckgo
from typing import Tuple, Any
import json

# Configuration constants
QUALITY_INDICATORS = [
    'source', 'data', 'research', 'study', 'analysis',
    'findings', 'results', 'conclusion', 'evidence'
]

# Define validation functions for task outputs
def data_quality_validator(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validates data quality and completeness for research tasks.
    """
    output_text = str(task_output.raw).lower()
    
    # Check for key quality indicators
    found_indicators = sum(1 for indicator in QUALITY_INDICATORS if indicator in output_text)
    
    if found_indicators >= 4:  # Require at least 4 quality indicators
        return True, task_output
    else:
        return False, f"Data quality insufficient. Found {found_indicators} quality indicators but need at least 4. Please include more research sources, data analysis, and evidence."

def completeness_validator(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validates that the analysis is complete and comprehensive.
    """
    output_text = str(task_output.raw)
    word_count = len(output_text.split())
    
    # Check for completeness indicators
    has_introduction = 'introduction' in output_text.lower() or output_text.startswith(('In ', 'The ', 'This '))
    has_conclusion = any(word in output_text.lower() for word in ['conclusion', 'summary', 'in summary', 'to conclude'])
    sufficient_length = word_count >= 100
    
    if has_introduction and has_conclusion and sufficient_length:
        return True, task_output
    else:
        missing = []
        if not has_introduction:
            missing.append("proper introduction")
        if not has_conclusion:
            missing.append("conclusion or summary")
        if not sufficient_length:
            missing.append(f"sufficient detail (need 100+ words, found {word_count})")
        
        return False, f"Analysis incomplete. Missing: {', '.join(missing)}. Please provide a more comprehensive response."

# Create specialized agents for the workflow
research_agent = Agent(
    name="ResearchAgent",
    role="Senior Research Analyst",
    goal="Conduct comprehensive research and gather high-quality data",
    backstory="You are a senior research analyst with expertise in data collection and analysis.",
    tools=[duckduckgo],
    instructions="Conduct thorough research using multiple sources. Provide detailed findings with proper citations and data analysis."
)

quality_checker = Agent(
    name="QualityChecker", 
    role="Quality Assurance Specialist",
    goal="Validate research quality and completeness",
    backstory="You are a QA specialist who ensures all research meets high standards of quality and completeness.",
    instructions="Review research outputs for quality, accuracy, and completeness. Provide specific feedback for improvements."
)

analyst = Agent(
    name="DataAnalyst",
    role="Data Analysis Expert", 
    goal="Analyze research data and identify key insights",
    backstory="You are a data analysis expert who can identify patterns, trends, and actionable insights from research data.",
    instructions="Analyze research data to identify key trends, patterns, and strategic insights. Provide data-driven recommendations."
)

decision_maker = Agent(
    name="DecisionMaker",
    role="Strategic Decision Maker",
    goal="Make strategic decisions based on analysis results",
    backstory="You are a strategic decision maker who evaluates analysis results and determines next steps.",
    instructions="Review analysis results and make strategic decisions about whether to proceed, modify approach, or conduct additional research."
)

report_writer = Agent(
    name="ReportWriter",
    role="Executive Report Writer",
    goal="Create comprehensive executive reports",
    backstory="You are an executive report writer who synthesizes research and analysis into actionable business reports.",
    instructions="Create comprehensive executive reports that synthesize research findings and analysis into clear, actionable recommendations."
)

# Define conditional task execution workflow

# Initial research task with quality validation
initial_research = Task(
    name="initial_research",
    description="Research the current state of renewable energy adoption in the business sector, including trends, challenges, and opportunities",
    expected_output="Comprehensive research report on renewable energy adoption in business",
    agent=research_agent,
    guardrail=data_quality_validator,
    max_retries=3
)

# Quality check task - conditional on research quality
quality_check = Task(
    name="quality_assessment",
    description="Assess the quality and completeness of the research findings. Determine if additional research is needed.",
    expected_output="Quality assessment report with go/no-go decision for proceeding to analysis",
    agent=quality_checker,
    context=[initial_research],
    guardrail=completeness_validator,
    max_retries=2
)

# Conditional task - only execute if quality check passes
data_analysis = Task(
    name="data_analysis",
    description="Analyze the research data to identify key trends, market opportunities, and strategic recommendations for renewable energy adoption",
    expected_output="Strategic analysis with key insights and recommendations",
    agent=analyst,
    context=[initial_research, quality_check],
    
    # Conditional execution based on quality check
    task_type="decision",
    condition={
        "proceed": ["final_report"],  # If analysis is good, proceed to final report
        "needs_more_research": ["additional_research"],  # If needs more data, do additional research
        "insufficient_data": []  # If data is insufficient, stop workflow
    }
)

# Additional research task (conditional execution)
additional_research = Task(
    name="additional_research", 
    description="Conduct additional targeted research to fill gaps identified in the quality assessment",
    expected_output="Supplementary research addressing identified gaps",
    agent=research_agent,
    context=[initial_research, quality_check],
    tools=[duckduckgo],
    guardrail=data_quality_validator,
    max_retries=2
)

# Decision point task
decision_task = Task(
    name="strategic_decision",
    description="Based on all available research and analysis, make a strategic decision about renewable energy investment recommendations",
    expected_output="Strategic decision with clear reasoning and recommended next steps",
    agent=decision_maker,
    context=[initial_research, quality_check, data_analysis],
    
    # This task determines the workflow path
    task_type="decision",
    condition={
        "high_confidence": ["final_report"],
        "medium_confidence": ["risk_analysis"], 
        "low_confidence": ["additional_research"]
    }
)

# Risk analysis task (conditional)
risk_analysis = Task(
    name="risk_analysis",
    description="Conduct detailed risk analysis for renewable energy investment recommendations",
    expected_output="Comprehensive risk assessment with mitigation strategies",
    agent=analyst,
    context=[initial_research, data_analysis, decision_task]
)

# Final report task
final_report = Task(
    name="final_report",
    description="Create a comprehensive executive report synthesizing all research, analysis, and strategic recommendations",
    expected_output="Executive report with strategic recommendations for renewable energy adoption",
    agent=report_writer,
    context=[initial_research, quality_check, data_analysis, decision_task],
    guardrail=completeness_validator,
    max_retries=2
)

# Create workflow with conditional execution
workflow = PraisonAIAgents(
    agents=[research_agent, quality_checker, analyst, decision_maker, report_writer],
    tasks=[
        initial_research, 
        quality_check, 
        data_analysis, 
        additional_research,  # Conditional
        decision_task,
        risk_analysis,        # Conditional
        final_report
    ],
    process="workflow",  # Use workflow process for conditional execution
    verbose=True
)

print("="*80)
print("EXECUTING ADVANCED TASK MANAGEMENT WORKFLOW")
print("="*80)
print("This workflow includes:")
print("- Quality validation with retry mechanisms")
print("- Conditional task execution based on results")
print("- Dynamic routing and decision points")
print("- Complex task dependencies")
print("="*80)

# Execute the conditional workflow
result = workflow.start()

print("\n" + "="*80)
print("ADVANCED TASK MANAGEMENT COMPLETED")
print("="*80)
print("This example demonstrated:")
print("- Conditional task execution based on validation results")
print("- Quality validation with specific feedback for improvements") 
print("- Dynamic workflow routing with decision points")
print("- Complex task dependencies and context passing")
print("- Retry mechanisms with iterative improvement")
print("- Multi-stage validation and quality assurance")
print(f"\nFinal Result Summary:\n{result}")