#!/usr/bin/env python3
"""
Stateful Workflow Example

Demonstrates advanced state management in multi-agent workflows with
persistence, conditional execution, and cross-task communication.
"""

from praisonaiagents import PraisonAIAgents, Agent, Task

def research_tool(topic: str, num_sources: int = 5):
    """Simulated research tool that updates workflow state"""
    # In a real implementation, this would perform actual research
    findings = [
        f"Finding 1 about {topic}: Key insight on applications",
        f"Finding 2 about {topic}: Recent breakthrough in methodology", 
        f"Finding 3 about {topic}: Performance benchmarks and comparisons"
    ][:num_sources]
    
    return {
        "topic": topic,
        "sources_found": len(findings),
        "findings": findings,
        "confidence": 0.85
    }

def analysis_tool(research_data: dict):
    """Simulated analysis tool"""
    findings = research_data.get("findings", [])
    analysis = {
        "key_themes": ["applications", "methodology", "performance"],
        "findings_count": len(findings),
        "confidence_score": research_data.get("confidence", 0.0),
        "recommendation": "Proceed with detailed investigation" if len(findings) >= 3 else "Need more research"
    }
    return analysis

def main():
    print("🔄 Stateful Workflow Example")
    print("=" * 50)
    
    # Create agents with tools
    researcher = Agent(
        name="Research Agent",
        role="AI Research Specialist",
        instructions="Conduct thorough research and track progress",
        tools=[research_tool]
    )
    
    analyzer = Agent(
        name="Analysis Agent", 
        role="Data Analysis Expert",
        instructions="Analyze research findings and provide insights",
        tools=[analysis_tool]
    )
    
    writer = Agent(
        name="Report Writer",
        role="Technical Writer",
        instructions="Create comprehensive reports based on analysis"
    )
    
    # Create tasks with conditional logic
    research_task = Task(
        name="research_task",
        description="Research the specified topic using available tools. Track findings in workflow state.",
        agent=researcher,
        expected_output="Research findings with confidence scores"
    )
    
    analysis_task = Task(
        name="analysis_task", 
        description="Analyze research findings if sufficient data is available. Use workflow state to check progress.",
        agent=analyzer,
        expected_output="Analysis summary with recommendations",
        context=[research_task]  # Depends on research task
    )
    
    report_task = Task(
        name="report_task",
        description="Write final report if analysis shows high confidence. Check workflow state for quality metrics.",
        agent=writer,
        expected_output="Final research report",
        context=[research_task, analysis_task]  # Depends on both previous tasks
    )
    
    # Create stateful workflow
    workflow = PraisonAIAgents(
        agents=[researcher, analyzer, writer],
        tasks=[research_task, analysis_task, report_task],
        memory=True,
        process="workflow",
        user_id="research_project_001",
        verbose=1
    )
    
    print(f"🤖 Created workflow with {len(workflow.agents)} agents and {len(workflow.tasks)} tasks")
    
    # Set initial workflow state
    workflow.set_state("research_topic", "artificial intelligence safety")
    workflow.set_state("target_sources", 5)
    workflow.set_state("quality_threshold", 0.8)
    workflow.set_state("project_deadline", "2024-12-31")
    
    print("📝 Set initial workflow state:")
    print(f"  Topic: {workflow.get_state('research_topic')}")
    print(f"  Target sources: {workflow.get_state('target_sources')}")
    print(f"  Quality threshold: {workflow.get_state('quality_threshold')}")
    
    # Save session state before starting
    workflow.save_session_state("ai_safety_research_session")
    print("💾 Saved session state")
    
    # Simulate workflow execution with state updates
    print("\n🚀 Starting workflow execution...")
    
    # Task 1: Research
    print("\n--- Research Phase ---")
    workflow.set_state("current_phase", "research")
    workflow.increment_state("tasks_completed", 0, default=0)
    
    # Simulate research execution
    topic = workflow.get_state("research_topic")
    target = workflow.get_state("target_sources", 5)
    
    research_result = research_tool(topic, target)
    workflow.set_state("research_results", research_result)
    workflow.increment_state("tasks_completed", 1)
    
    print(f"✅ Research completed: {research_result['sources_found']} sources found")
    
    # Task 2: Analysis (conditional on research quality)
    print("\n--- Analysis Phase ---")
    research_data = workflow.get_state("research_results", {})
    
    if research_data.get("sources_found", 0) >= 3:
        workflow.set_state("current_phase", "analysis")
        
        analysis_result = analysis_tool(research_data)
        workflow.set_state("analysis_results", analysis_result)
        workflow.increment_state("tasks_completed", 1)
        
        print(f"✅ Analysis completed: {analysis_result['recommendation']}")
    else:
        workflow.set_state("current_phase", "research_insufficient")
        print("⚠️ Insufficient research data for analysis")
    
    # Task 3: Report Writing (conditional on analysis confidence)
    print("\n--- Report Writing Phase ---")
    analysis_data = workflow.get_state("analysis_results", {})
    quality_threshold = workflow.get_state("quality_threshold", 0.8)
    
    if analysis_data.get("confidence_score", 0) >= quality_threshold:
        workflow.set_state("current_phase", "report_writing")
        
        # Simulate report writing
        report_sections = ["Introduction", "Research Findings", "Analysis", "Conclusions"]
        workflow.set_state("report_sections", report_sections)
        workflow.increment_state("tasks_completed", 1)
        
        print(f"✅ Report completed with {len(report_sections)} sections")
    else:
        workflow.set_state("current_phase", "quality_insufficient")
        print("⚠️ Analysis confidence too low for final report")
    
    # Display final workflow state
    print("\n📊 Final Workflow State:")
    print("=" * 30)
    
    all_state = workflow.get_all_state()
    for key, value in all_state.items():
        if isinstance(value, dict):
            print(f"  {key}: {type(value).__name__} with {len(value)} items")
        elif isinstance(value, list):
            print(f"  {key}: {len(value)} items")
        else:
            print(f"  {key}: {value}")
    
    # Demonstrate state persistence
    print("\n🔄 Demonstrating state persistence...")
    
    # Save current state
    session_id = "ai_safety_research_session"
    workflow.save_session_state(session_id)
    
    # Clear state and restore
    print("Clearing state...")
    workflow.clear_state()
    print(f"State after clearing: {len(workflow.get_all_state())} items")
    
    print("Restoring state...")
    restored = workflow.restore_session_state(session_id)
    print(f"State restoration: {'✅ Success' if restored else '❌ Failed'}")
    print(f"State after restoring: {len(workflow.get_all_state())} items")
    
    # Demonstrate convenience methods
    print("\n🛠️ Demonstrating convenience methods:")
    
    # Check if keys exist
    has_topic = workflow.has_state("research_topic")
    has_results = workflow.has_state("research_results")
    print(f"Has research topic: {has_topic}")
    print(f"Has research results: {has_results}")
    
    # Work with list state
    workflow.append_to_state("project_notes", "Initial research phase completed")
    workflow.append_to_state("project_notes", "Analysis phase successful") 
    workflow.append_to_state("project_notes", "Report writing finalized")
    
    notes = workflow.get_state("project_notes", [])
    print(f"Project notes: {len(notes)} entries")
    for i, note in enumerate(notes, 1):
        print(f"  {i}. {note}")
    
    # Increment counters
    final_tasks = workflow.get_state("tasks_completed", 0)
    print(f"Total tasks completed: {final_tasks}")
    
    print("\n✅ Stateful workflow example completed!")
    print("The workflow maintained state across all phases and demonstrated persistence.")

if __name__ == "__main__":
    main()