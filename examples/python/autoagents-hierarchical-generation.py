"""
AutoAgents Hierarchical Generation Example

This example demonstrates AutoAgents' ability to automatically generate
hierarchical agent structures and complex workflows from natural language descriptions.
"""

from praisonaiagents import AutoAgents, Agent, Task

print("=== AutoAgents Hierarchical Generation Example ===\n")

# Example 1: Generate agents for market research project
print("Example 1: Market Research Project")
print("-" * 40)

market_research_description = """
Create a comprehensive market research team to analyze the electric vehicle market.
We need agents for data collection, competitive analysis, customer surveys, 
financial modeling, and final report generation.
"""

auto_agents_1 = AutoAgents()
result_1 = auto_agents_1.generate_and_execute(market_research_description)

print(f"Generated Agents: {len(result_1['agents'])}")
for agent in result_1['agents']:
    print(f"  - {agent.name}: {agent.role}")
print(f"Generated Tasks: {len(result_1['tasks'])}")
print(f"Result: {result_1['final_output'][:200]}...\n")

# Example 2: Generate hierarchical software development team
print("Example 2: Software Development Team")
print("-" * 40)

software_dev_description = """
Build a software development team to create a mobile app for food delivery.
Include product manager, technical lead, frontend developer, backend developer,
QA engineer, and DevOps specialist. Each should have specific responsibilities
and work in proper sequence.
"""

auto_agents_2 = AutoAgents(max_agents=6, hierarchy_levels=2)
result_2 = auto_agents_2.generate_and_execute(software_dev_description)

print(f"Generated Agents: {len(result_2['agents'])}")
print("Hierarchy Structure:")
for level, agents in result_2['hierarchy'].items():
    print(f"  Level {level}: {[agent.name for agent in agents]}")
print(f"Final Output: {result_2['final_output'][:200]}...\n")

# Example 3: Custom agent templates for specialized domain
print("Example 3: Custom Templates for Healthcare")
print("-" * 40)

# Define custom agent templates for healthcare domain
healthcare_templates = {
    "Medical Researcher": {
        "role": "Medical Research Specialist",
        "backstory": "Expert in medical literature review and clinical research",
        "capabilities": ["literature_search", "data_analysis", "evidence_synthesis"]
    },
    "Clinical Advisor": {
        "role": "Clinical Practice Advisor", 
        "backstory": "Practicing physician with expertise in patient care protocols",
        "capabilities": ["clinical_guidelines", "patient_assessment", "treatment_planning"]
    },
    "Regulatory Specialist": {
        "role": "Healthcare Regulatory Expert",
        "backstory": "Expert in FDA regulations and healthcare compliance",
        "capabilities": ["regulatory_analysis", "compliance_check", "approval_guidance"]
    }
}

healthcare_description = """
Create a team to evaluate a new medical device for regulatory approval.
Need comprehensive research, clinical assessment, and regulatory guidance.
"""

auto_agents_3 = AutoAgents(
    agent_templates=healthcare_templates,
    domain_expertise="healthcare",
    compliance_requirements=True
)
result_3 = auto_agents_3.generate_and_execute(healthcare_description)

print(f"Healthcare Team Generated: {len(result_3['agents'])} agents")
for agent in result_3['agents']:
    print(f"  - {agent.name}: {agent.role}")
print(f"Compliance Score: {result_3['compliance_score']}/100")
print(f"Result: {result_3['final_output'][:200]}...\n")

# Example 4: Dynamic scaling based on workload
print("Example 4: Dynamic Agent Scaling")
print("-" * 40)

complex_description = """
Organize a large-scale event with 10,000 attendees. Handle venue booking,
catering, entertainment, security, marketing, registration, logistics,
vendor management, and post-event analysis.
"""

auto_agents_4 = AutoAgents(
    auto_scaling=True,
    max_agents=12,
    workload_threshold=0.8,
    optimization_strategy="efficiency"
)
result_4 = auto_agents_4.generate_and_execute(complex_description)

print(f"Scaled to {len(result_4['agents'])} agents for complex project")
print("Workload Distribution:")
for agent in result_4['agents']:
    workload = result_4['workload_metrics'][agent.name]
    print(f"  - {agent.name}: {workload['utilization']:.1%} utilization")
print(f"Overall Efficiency: {result_4['efficiency_score']:.1%}\n")

# Example 5: Iterative improvement and learning
print("Example 5: Iterative Improvement")
print("-" * 40)

learning_description = """
Build a customer service team that can handle technical support,
billing inquiries, and product recommendations. The team should
learn from each interaction and improve responses.
"""

auto_agents_5 = AutoAgents(
    learning_enabled=True,
    feedback_integration=True,
    continuous_improvement=True
)

# First iteration
result_5a = auto_agents_5.generate_and_execute(learning_description)
print(f"Initial Generation: {len(result_5a['agents'])} agents")
print(f"Performance Score: {result_5a['performance_score']:.2f}")

# Simulate feedback and improvement
feedback = {
    "response_quality": 0.7,
    "resolution_rate": 0.8,
    "customer_satisfaction": 0.75,
    "areas_for_improvement": ["faster_response", "better_technical_knowledge"]
}

auto_agents_5.integrate_feedback(feedback)
result_5b = auto_agents_5.regenerate_improved()

print(f"After Improvement: {len(result_5b['agents'])} agents")
print(f"Improved Performance Score: {result_5b['performance_score']:.2f}")
print(f"Improvement: +{result_5b['performance_score'] - result_5a['performance_score']:.2f}")

# Display final statistics
print("\n=== Final Statistics ===")
print(f"Total Agents Generated: {sum(len(r['agents']) for r in [result_1, result_2, result_3, result_4, result_5b])}")
print(f"Total Tasks Created: {sum(len(r['tasks']) for r in [result_1, result_2, result_3, result_4, result_5b])}")
print(f"Success Rate: {sum(r.get('success', True) for r in [result_1, result_2, result_3, result_4, result_5b])/5:.1%}")
print("AutoAgents demonstration complete!")