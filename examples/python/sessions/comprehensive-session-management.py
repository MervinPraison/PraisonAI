"""
Comprehensive Session Management Example

This example demonstrates advanced session management capabilities including
session persistence, recovery, state management, and multi-session coordination.

Features demonstrated:
- Session creation and persistence
- State management across sessions
- Session recovery after interruption
- Multi-user session coordination
- Session-specific memory and knowledge
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.session import Session
from praisonaiagents.tools import duckduckgo
import tempfile
import os
import json

# Create a temporary directory for session storage
session_dir = tempfile.mkdtemp()
print(f"Session storage directory: {session_dir}")
try:
    # Create agents for session-based workflows
    research_agent = Agent(
        name="SessionResearcher",
        role="Research Specialist",
        goal="Conduct research while maintaining session context",
        backstory="You are a research specialist who maintains context across multiple sessions and can resume work from where you left off.",
        tools=[duckduckgo],
        instructions="Conduct thorough research and maintain awareness of previous session context when available."
    )

    analysis_agent = Agent(
        name="SessionAnalyst", 
        role="Data Analyst",
        goal="Analyze data while preserving session state",
        backstory="You are a data analyst who can maintain analysis context across sessions and build upon previous work.",
        instructions="Analyze research data and build upon any previous analysis from earlier sessions."
    )

    # Session 1: Initial Research Session
    print("="*70)
    print("SESSION 1: INITIAL RESEARCH SESSION")
    print("="*70)

    # Create first session
    session1 = Session(
        session_id="research_project_001",
        user_id="user_researcher_01",
        storage_path=session_dir
    )

    # Create initial research task
    research_task1 = Task(
        name="initial_research",
        description="Research the latest trends in sustainable technology for manufacturing",
        expected_output="Comprehensive research report on sustainable manufacturing technology trends",
        agent=research_agent
    )

    # Create agents with session
    agents_session1 = PraisonAIAgents(
        agents=[research_agent],
        tasks=[research_task1],
        session=session1,
        verbose=True
    )

    # Execute first session
    print("Starting initial research session...")
    result1 = agents_session1.start()

    # Save session state
    session1.save()
    print(f"Session 1 completed and saved. Result preview: {str(result1)[:200]}...")

    # Session 2: Analysis Session (same user, continuation)
    print("\n" + "="*70)
    print("SESSION 2: ANALYSIS SESSION (CONTINUING WORK)")
    print("="*70)

    # Create second session for analysis
    session2 = Session(
        session_id="research_project_002", 
        user_id="user_researcher_01",  # Same user
        storage_path=session_dir
    )

    # Load previous session context (simulating session recovery)
    # In real usage, you might load from database or persistent storage
    session2.set_state("previous_research_summary", str(result1)[:500])

    analysis_task = Task(
        name="trend_analysis",
        description="Analyze the research findings to identify the top 5 most promising sustainable manufacturing technologies",
        expected_output="Analysis report with top 5 sustainable manufacturing technologies and their potential impact",
        agent=analysis_agent,
        # Pass context from previous session
        context_variables={"previous_research": str(result1)}
    )

    agents_session2 = PraisonAIAgents(
        agents=[analysis_agent],
        tasks=[analysis_task], 
        session=session2,
        verbose=True
    )

    print("Starting analysis session with previous context...")
    result2 = agents_session2.start()

    # Save session state
    session2.save()
    print(f"Session 2 completed and saved. Result preview: {str(result2)[:200]}...")

    # Session 3: Recovery Demonstration
    print("\n" + "="*70)
    print("SESSION 3: RECOVERY DEMONSTRATION")
    print("="*70)

    # Simulate session recovery after interruption
    recovery_session = Session(
        session_id="research_project_recovery",
        user_id="user_researcher_01",
        storage_path=session_dir
    )

    # Load state from previous sessions
    recovery_session.set_state("research_summary", str(result1)[:300])
    recovery_session.set_state("analysis_summary", str(result2)[:300])

    # Create a synthesis task that uses recovered session state
    synthesis_agent = Agent(
        name="SynthesisAgent",
        role="Research Synthesizer", 
        goal="Synthesize research and analysis into actionable recommendations",
        backstory="You synthesize research and analysis from multiple sessions into comprehensive recommendations.",
        instructions="Use the session context to create comprehensive recommendations based on all previous work."
    )

    synthesis_task = Task(
        name="synthesis_report",
        description="Create a comprehensive synthesis report with actionable recommendations based on all previous research and analysis",
        expected_output="Executive synthesis report with strategic recommendations",
        agent=synthesis_agent,
        # Access session state
        context_variables={
            "research_context": recovery_session.get_state("research_summary"),
            "analysis_context": recovery_session.get_state("analysis_summary")
        }
    )

    agents_recovery = PraisonAIAgents(
        agents=[synthesis_agent],
        tasks=[synthesis_task],
        session=recovery_session,
        verbose=True
    )

    print("Starting recovery session with full context from previous sessions...")
    result3 = agents_recovery.start()

    # Save final session
    recovery_session.save()
    print(f"Recovery session completed. Result preview: {str(result3)[:200]}...")

    # Session 4: Multi-User Coordination Demo
    print("\n" + "="*70) 
    print("SESSION 4: MULTI-USER COORDINATION DEMO")
    print("="*70)

    # Create sessions for different users working on the same project
    reviewer_session = Session(
        session_id="peer_review_001",
        user_id="user_reviewer_01",  # Different user
        storage_path=session_dir
    )

    # Reviewer can access shared project context
    reviewer_session.set_state("shared_research", str(result1)[:400])
    reviewer_session.set_state("shared_analysis", str(result2)[:400])
    reviewer_session.set_state("shared_synthesis", str(result3)[:400])

    review_agent = Agent(
        name="PeerReviewer",
        role="Research Peer Reviewer",
        goal="Provide expert peer review of research, analysis, and synthesis",
        backstory="You are a peer reviewer who evaluates research quality and provides constructive feedback.",
        instructions="Review all provided work and provide constructive feedback with specific suggestions for improvement."
    )

    review_task = Task(
        name="peer_review",
        description="Conduct peer review of the research project including research, analysis, and synthesis phases",
        expected_output="Comprehensive peer review with specific feedback and recommendations for improvement",
        agent=review_agent,
        context_variables={
            "research_to_review": reviewer_session.get_state("shared_research"),
            "analysis_to_review": reviewer_session.get_state("shared_analysis"), 
            "synthesis_to_review": reviewer_session.get_state("shared_synthesis")
        }
    )

    agents_reviewer = PraisonAIAgents(
        agents=[review_agent],
        tasks=[review_task],
        session=reviewer_session,
        verbose=True
    )

    print("Starting peer review session by different user...")
    result4 = agents_reviewer.start()

    # Save reviewer session
    reviewer_session.save()
    print(f"Peer review session completed. Result preview: {str(result4)[:200]}...")

    # Session Summary and Cleanup
    print("\n" + "="*80)
    print("SESSION MANAGEMENT DEMONSTRATION SUMMARY")
    print("="*80)

    # Display session information
    print("Sessions created:")
    print(f"1. Research Session (ID: research_project_001, User: user_researcher_01)")
    print(f"2. Analysis Session (ID: research_project_002, User: user_researcher_01)")  
    print(f"3. Recovery Session (ID: research_project_recovery, User: user_researcher_01)")
    print(f"4. Review Session (ID: peer_review_001, User: user_reviewer_01)")

    print("\nSession capabilities demonstrated:")
    print("- Session persistence and state management")
    print("- Context passing between sessions")
    print("- Session recovery after interruption")
    print("- Multi-user session coordination")
    print("- State sharing across different users")
    print("- Session-specific task execution")

    # List session files created
    session_files = [f for f in os.listdir(session_dir) if f.endswith('.json')]
    print(f"\nSession files created: {len(session_files)}")
    for file in session_files:
        print(f"  - {file}")

finally:
    # Cleanup
    import shutil
    shutil.rmtree(session_dir)
    print(f"\nCleanup completed. Temporary session directory removed.")