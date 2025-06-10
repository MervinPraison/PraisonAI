"""
State with Memory Integration Example
====================================

This example demonstrates:
1. Using shared memory for state persistence
2. State sharing between agents via memory
3. Combining workflow state with memory storage
4. Historical state tracking
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.memory import Memory
from typing import Dict, Any, List
import json
import time
from datetime import datetime

# Initialize shared memory
memory_config = {
    "config": {
        "collection_name": "state_memory_demo",
        "path": "./state_memory_db"
    }
}

shared_memory = Memory(**memory_config)

# Tool functions that use both state and memory
def initialize_conversation_state(user_name: str, topic: str) -> Dict[str, Any]:
    """Initialize conversation state and store in memory"""
    # Set workflow state
    workflow.set_state("user_name", user_name)
    workflow.set_state("topic", topic)
    workflow.set_state("start_time", time.time())
    workflow.set_state("turn_count", 0)
    workflow.set_state("conversation_history", [])
    
    # Store in memory for persistence
    context = f"Starting conversation with {user_name} about {topic}"
    shared_memory.add(
        text=context,
        metadata={
            "type": "conversation_start",
            "user": user_name,
            "topic": topic,
            "timestamp": datetime.now().isoformat()
        }
    )
    
    return {
        "status": "initialized",
        "user": user_name,
        "topic": topic,
        "memory_stored": True
    }

def add_conversation_turn(speaker: str, message: str) -> Dict[str, Any]:
    """Add a conversation turn to state and memory"""
    # Get current state
    history = workflow.get_state("conversation_history", [])
    turn_count = workflow.get_state("turn_count", 0)
    
    # Create turn entry
    turn = {
        "turn": turn_count + 1,
        "speaker": speaker,
        "message": message,
        "timestamp": time.time()
    }
    
    # Update state
    history.append(turn)
    workflow.set_state("conversation_history", history)
    workflow.set_state("turn_count", turn_count + 1)
    workflow.set_state(f"last_{speaker}_message", message)
    
    # Store in memory
    shared_memory.add(
        text=f"{speaker}: {message}",
        metadata={
            "type": "conversation_turn",
            "speaker": speaker,
            "turn": turn_count + 1,
            "topic": workflow.get_state("topic"),
            "user": workflow.get_state("user_name")
        }
    )
    
    return {
        "turn_added": turn,
        "total_turns": turn_count + 1,
        "history_length": len(history)
    }

def search_conversation_memory(query: str, speaker: str = None) -> Dict[str, Any]:
    """Search through conversation memory"""
    # Build metadata filter
    metadata_filter = {"type": "conversation_turn"}
    if speaker:
        metadata_filter["speaker"] = speaker
    
    # Search memory
    results = shared_memory.search(
        query=query,
        n=5,
        metadata_filter=metadata_filter
    )
    
    # Update state with search results
    workflow.set_state("last_search_query", query)
    workflow.set_state("last_search_results", len(results))
    
    return {
        "query": query,
        "results_count": len(results),
        "results": [
            {
                "text": r["text"],
                "speaker": r["metadata"].get("speaker"),
                "turn": r["metadata"].get("turn"),
                "relevance": r.get("score", 0)
            }
            for r in results
        ]
    }

def analyze_conversation_patterns() -> Dict[str, Any]:
    """Analyze patterns in conversation using state and memory"""
    # Get state data
    history = workflow.get_state("conversation_history", [])
    user_name = workflow.get_state("user_name", "Unknown")
    topic = workflow.get_state("topic", "Unknown")
    
    # Calculate metrics from state
    total_turns = len(history)
    speakers = {}
    
    for turn in history:
        speaker = turn["speaker"]
        speakers[speaker] = speakers.get(speaker, 0) + 1
    
    # Search memory for related conversations
    related_convos = shared_memory.search(
        query=topic,
        n=10,
        metadata_filter={"type": "conversation_turn"}
    )
    
    # Analyze patterns
    patterns = {
        "current_conversation": {
            "user": user_name,
            "topic": topic,
            "total_turns": total_turns,
            "speaker_distribution": speakers,
            "duration_seconds": time.time() - workflow.get_state("start_time", time.time())
        },
        "memory_insights": {
            "related_conversations": len(related_convos),
            "common_speakers": list(set(r["metadata"].get("speaker") for r in related_convos)),
            "topics_discussed": list(set(r["metadata"].get("topic") for r in related_convos))
        }
    }
    
    # Store analysis in state
    workflow.set_state("conversation_analysis", patterns)
    
    return patterns

def retrieve_user_history(user_name: str) -> Dict[str, Any]:
    """Retrieve all historical data for a user from memory"""
    # Search memory for user's conversations
    user_history = shared_memory.search(
        query=user_name,
        n=20,
        metadata_filter={"user": user_name}
    )
    
    # Organize by conversation topics
    topics = {}
    for item in user_history:
        topic = item["metadata"].get("topic", "Unknown")
        if topic not in topics:
            topics[topic] = []
        topics[topic].append({
            "text": item["text"],
            "type": item["metadata"].get("type"),
            "timestamp": item["metadata"].get("timestamp")
        })
    
    # Update state with user history
    workflow.set_state("user_history_retrieved", True)
    workflow.set_state("user_topics", list(topics.keys()))
    
    return {
        "user": user_name,
        "total_interactions": len(user_history),
        "topics_discussed": list(topics.keys()),
        "conversation_count": len(topics),
        "history_by_topic": topics
    }

def summarize_and_save_state() -> Dict[str, Any]:
    """Create a summary of the conversation and save final state"""
    # Get all conversation data
    history = workflow.get_state("conversation_history", [])
    analysis = workflow.get_state("conversation_analysis", {})
    user_name = workflow.get_state("user_name")
    topic = workflow.get_state("topic")
    
    # Create summary
    summary = {
        "conversation_id": f"{user_name}_{topic}_{int(time.time())}",
        "user": user_name,
        "topic": topic,
        "total_turns": len(history),
        "duration": time.time() - workflow.get_state("start_time", 0),
        "participants": list(set(turn["speaker"] for turn in history)),
        "key_points": [turn["message"][:50] + "..." for turn in history[-3:]],  # Last 3 messages
        "analysis": analysis
    }
    
    # Save summary to memory
    shared_memory.add(
        text=json.dumps(summary, indent=2),
        metadata={
            "type": "conversation_summary",
            "user": user_name,
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "conversation_id": summary["conversation_id"]
        }
    )
    
    # Clear workflow state but keep summary
    workflow.set_state("final_summary", summary)
    workflow.set_state("state_saved_to_memory", True)
    
    return summary

# Create agents with memory-aware tools
conversation_manager = Agent(
    name="ConversationManager",
    role="Manage conversation state and memory",
    goal="Initialize and track conversation state effectively",
    backstory="Expert in conversation management and state tracking",
    tools=[initialize_conversation_state, add_conversation_turn, summarize_and_save_state],
    memory=shared_memory,
    llm="gpt-4o-mini"
)

memory_analyst = Agent(
    name="MemoryAnalyst",
    role="Analyze conversation patterns from memory",
    goal="Extract insights from conversation history",
    backstory="Specialist in pattern recognition and memory analysis",
    tools=[search_conversation_memory, analyze_conversation_patterns, retrieve_user_history],
    memory=shared_memory,
    llm="gpt-4o-mini"
)

# Create tasks
init_conversation_task = Task(
    name="init_conversation",
    description="Initialize a conversation with user 'Alice' about 'AI and Future of Work'",
    expected_output="Initialization status",
    agent=conversation_manager,
    tools=[initialize_conversation_state]
)

simulate_conversation_task = Task(
    name="simulate_conversation",
    description="""Simulate a conversation by adding these turns:
    1. Alice: "What are the main impacts of AI on employment?"
    2. Assistant: "AI is transforming employment through automation and augmentation."
    3. Alice: "Which industries are most affected?"
    4. Assistant: "Manufacturing, customer service, and data analysis see significant changes."
    5. Alice: "How can workers prepare for these changes?"
    
    Use add_conversation_turn for each message.""",
    expected_output="Conversation simulation results",
    agent=conversation_manager,
    tools=[add_conversation_turn],
    context=[init_conversation_task]
)

search_memory_task = Task(
    name="search_memory",
    description="""Search conversation memory for:
    1. Messages about 'automation'
    2. All messages from 'Alice'
    3. Messages about 'employment'""",
    expected_output="Search results from memory",
    agent=memory_analyst,
    tools=[search_conversation_memory],
    context=[simulate_conversation_task]
)

analyze_patterns_task = Task(
    name="analyze_patterns",
    description="Analyze conversation patterns and extract insights",
    expected_output="Pattern analysis results",
    agent=memory_analyst,
    tools=[analyze_conversation_patterns],
    context=[search_memory_task]
)

retrieve_history_task = Task(
    name="retrieve_history",
    description="Retrieve all historical data for user 'Alice'",
    expected_output="User history summary",
    agent=memory_analyst,
    tools=[retrieve_user_history],
    context=[analyze_patterns_task]
)

save_state_task = Task(
    name="save_state",
    description="Create final summary and save conversation state to memory",
    expected_output="Final conversation summary",
    agent=conversation_manager,
    tools=[summarize_and_save_state],
    context=[retrieve_history_task]
)

# Create workflow with shared memory
workflow = PraisonAIAgents(
    agents=[conversation_manager, memory_analyst],
    tasks=[
        init_conversation_task,
        simulate_conversation_task,
        search_memory_task,
        analyze_patterns_task,
        retrieve_history_task,
        save_state_task
    ],
    memory=memory_config,  # This creates shared memory for all agents
    verbose=1,
    process="sequential"
)

# Run workflow
print("\n=== State with Memory Integration Demo ===")
print("\n1. Starting workflow with memory-based state management...")
result = workflow.start()

# Display results
print("\n2. Final State Summary:")
final_summary = workflow.get_state("final_summary", {})
if final_summary:
    print(f"   Conversation ID: {final_summary.get('conversation_id')}")
    print(f"   Total Turns: {final_summary.get('total_turns')}")
    print(f"   Duration: {final_summary.get('duration', 0):.2f} seconds")
    print(f"   Participants: {final_summary.get('participants')}")

print("\n3. Memory Storage Status:")
print(f"   State saved to memory: {workflow.get_state('state_saved_to_memory', False)}")
print(f"   User history retrieved: {workflow.get_state('user_history_retrieved', False)}")
print(f"   Topics in memory: {workflow.get_state('user_topics', [])}")

# Test memory persistence by creating new workflow instance
print("\n4. Testing Memory Persistence:")
print("   Creating new workflow instance to test memory retrieval...")

# Create a simple test agent to verify memory persistence
test_agent = Agent(
    name="MemoryTester",
    role="Test memory persistence",
    goal="Verify stored conversation data",
    backstory="Memory system tester",
    tools=[search_conversation_memory],
    memory=shared_memory,
    llm="gpt-4o-mini"
)

test_task = Task(
    name="test_memory",
    description="Search memory for 'Alice' to verify persistence",
    expected_output="Memory search results",
    agent=test_agent,
    tools=[search_conversation_memory]
)

test_workflow = PraisonAIAgents(
    agents=[test_agent],
    tasks=[test_task],
    memory=memory_config,
    verbose=0
)

# This will use the same memory collection and find previously stored data
test_result = test_workflow.start()

print("\n=== Demo Complete ===")
print("\nNote: The conversation data has been persisted in memory and can be")
print("retrieved in future sessions using the same memory configuration.")