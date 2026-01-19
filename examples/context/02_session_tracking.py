"""
Session Tracking Example

Demonstrates tracking conversation state (goal, plan, progress) across turns.
Inspired by Agno's SessionContextStore pattern.
"""

from praisonaiagents.context import SessionContextTracker

# Create session tracker
tracker = SessionContextTracker(
    session_id="user123",
    track_summary=True,
    track_goal=True,
    track_plan=True,
    track_progress=True,
)

# Set the user's goal
tracker.update_goal("Build a Python web application with Flask")

# Define the plan
tracker.update_plan([
    "Create Flask project structure",
    "Add routes for API endpoints",
    "Implement database models",
    "Add authentication",
    "Write tests",
    "Deploy to cloud"
])

# Mark completed steps
tracker.add_progress("Created Flask project structure")
tracker.add_progress("Added routes for API endpoints")

# Update summary
tracker.update_summary(
    "User is building a Flask web app. Completed project setup and API routes. "
    "Next: implement database models."
)

if __name__ == "__main__":
    print("=== Session Tracking Example ===")
    print()
    
    # Show current state
    print(f"Session ID: {tracker.session_id}")
    print(f"Goal: {tracker.goal}")
    print(f"Plan: {tracker.plan}")
    print(f"Progress: {tracker.progress}")
    print()
    
    # Get context string (simple format)
    print("=== Context String ===")
    print(tracker.to_context_string())
    print()
    
    # Get system prompt section (XML format with guidelines)
    print("=== System Prompt Section ===")
    print(tracker.to_system_prompt_section())
    print()
    
    # Export to dict for persistence
    print("=== Export as Dict ===")
    data = tracker.to_dict()
    print(f"Exported: {data.keys()}")
    print()
    
    # Recreate from dict
    new_tracker = SessionContextTracker.from_dict(data)
    print(f"Restored goal: {new_tracker.goal}")
