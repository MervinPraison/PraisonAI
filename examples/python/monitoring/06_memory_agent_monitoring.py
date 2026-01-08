"""
Memory Agent with Performance Monitoring - Example 6

Demonstrates performance monitoring for agents with memory capabilities:
- Memory storage and retrieval timing
- Knowledge base operations
- Session persistence performance
- Memory search optimization

Shows how to monitor performance in stateful agents.
"""

import time
from praisonaiagents import Agent
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, get_performance_report,
    get_slowest_functions, analyze_performance_trends
)

# Simulate memory operations since actual memory might not be available
@monitor_function("memory_storage")
def store_memory(key: str, value: str, memory_type: str = "short_term"):
    """Simulate memory storage operation with monitoring."""
    print(f"💾 Storing {memory_type} memory: {key}")
    # Simulate storage time - short term is faster
    storage_time = 0.05 if memory_type == "short_term" else 0.15
    time.sleep(storage_time)
    return f"Stored {key} in {memory_type} memory"

@monitor_function("memory_retrieval") 
def retrieve_memory(key: str, memory_type: str = "short_term"):
    """Simulate memory retrieval operation with monitoring."""
    print(f"🔍 Retrieving {memory_type} memory: {key}")
    # Simulate retrieval time
    retrieval_time = 0.03 if memory_type == "short_term" else 0.12
    time.sleep(retrieval_time)
    return f"Retrieved {key} from {memory_type} memory"

@monitor_function("knowledge_search")
def search_knowledge_base(query: str):
    """Simulate knowledge base search with monitoring."""
    print(f"📚 Searching knowledge base for: {query}")
    # Simulate vector search time
    time.sleep(0.08)
    return f"Knowledge search results for: {query}"

@monitor_function("memory_consolidation")
def consolidate_memories(session_id: str):
    """Simulate memory consolidation process."""
    print(f"🔄 Consolidating memories for session: {session_id}")
    
    # Simulate consolidation steps
    store_memory("consolidated_session", session_id, "long_term")
    retrieve_memory("recent_interactions", "short_term")
    
    time.sleep(0.1)
    return f"Memories consolidated for session: {session_id}"

@monitor_function("stateful_agent_interaction")
def run_stateful_agent(query: str, session_id: str, conversation_turn: int):
    """Run agent with memory operations and monitoring."""
    
    # Simulate memory-enabled agent
    agent = Agent(
        instructions="""You are a memory-enabled AI assistant. You can remember 
        previous conversations and build on past interactions. Use your memory 
        to provide personalized and contextual responses.""",
        llm="gpt-4o-mini"
    )
    
    # Pre-processing: retrieve relevant memories
    with track_api_call("memory_preprocessing"):
        print(f"🧠 Pre-processing memories for turn {conversation_turn}")
        
        # Retrieve session context
        if conversation_turn > 1:
            retrieve_memory(f"session_{session_id}", "short_term")
        
        # Search for relevant knowledge
        search_knowledge_base(query)
        
        time.sleep(0.05)  # Simulate context preparation
    
    # Main agent execution
    with track_api_call("memory_agent_execution"):
        print(f"🚀 Processing query with memory context...")
        result = agent.start(query)
    
    # Post-processing: store new memories
    with track_api_call("memory_postprocessing"):
        print(f"💭 Post-processing: storing interaction memories")
        
        # Store the interaction
        store_memory(f"interaction_{conversation_turn}", query, "short_term")
        store_memory(f"response_{conversation_turn}", result, "short_term")
        
        # Update session memory
        store_memory(f"session_{session_id}", f"Turn {conversation_turn} completed", "short_term")
        
        time.sleep(0.03)  # Simulate memory update
    
    return result

@monitor_function("multi_turn_conversation")
def simulate_multi_turn_conversation():
    """Simulate a multi-turn conversation with memory."""
    session_id = "demo_session_001"
    
    conversation = [
        "Hello, I'm interested in learning about machine learning",
        "What are the main types of machine learning algorithms?",
        "Can you give me examples of supervised learning?",
        "How does this relate to what we discussed about machine learning earlier?"
    ]
    
    results = []
    
    for turn, query in enumerate(conversation, 1):
        print(f"\n💬 Conversation Turn {turn}")
        print(f"User: {query}")
        
        result = run_stateful_agent(query, session_id, turn)
        results.append(result)
        
        print(f"Agent: {result[:100]}..." if len(result) > 100 else f"Agent: {result}")
        
        # Simulate user thinking time
        time.sleep(0.1)
    
    # End of conversation: consolidate memories
    consolidate_memories(session_id)
    
    return results

def main():
    """Main function demonstrating memory agent performance monitoring."""
    print("=" * 70)
    print("EXAMPLE 6: Memory Agent Performance Monitoring")
    print("=" * 70)
    
    # Warm up the memory system
    print("\n🚀 Phase 1: Memory System Initialization")
    store_memory("system_initialized", "true", "long_term")
    search_knowledge_base("initialization")
    
    # Run multi-turn conversation
    print("\n💬 Phase 2: Multi-Turn Conversation with Memory")
    conversation_results = simulate_multi_turn_conversation()
    
    # Memory performance analysis
    print("\n" + "=" * 70)
    print("📊 MEMORY PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    # Performance trends analysis
    print("\n📈 Performance Trends:")
    try:
        trends = analyze_performance_trends()
        print(f"  Performance trend analysis completed")
        if trends:
            print(f"  Functions analyzed: {len(trends.get('functions', []))}")
    except Exception as e:
        print(f"  Trends analysis: {str(e)}")
    
    # Slowest operations
    print("\n🐌 Slowest Memory Operations:")
    slowest = get_slowest_functions()
    for func_name, avg_time in slowest[:5]:  # Top 5 slowest
        print(f"  {func_name}: {avg_time:.3f}s average")
    
    # Memory operation breakdown
    print("\n💾 Memory Operation Breakdown:")
    from praisonaiagents.telemetry import get_function_stats
    stats = get_function_stats()
    
    memory_operations = {k: v for k, v in stats.items() if 'memory' in k.lower()}
    
    for op_name, data in memory_operations.items():
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        print(f"  {op_name}:")
        print(f"    Operations: {data['call_count']}")
        print(f"    Avg Time: {avg_time:.3f}s")
        print(f"    Total Time: {data['total_time']:.3f}s")
    
    # Session efficiency metrics
    total_memory_ops = sum(data['call_count'] for data in memory_operations.values())
    total_memory_time = sum(data['total_time'] for data in memory_operations.values())
    
    print(f"\n🔍 Session Efficiency:")
    print(f"  Total Memory Operations: {total_memory_ops}")
    print(f"  Total Memory Time: {total_memory_time:.3f}s")
    print(f"  Avg Time per Memory Op: {total_memory_time/total_memory_ops:.3f}s" if total_memory_ops > 0 else "  No memory operations")
    
    # Performance report
    print("\n📋 Comprehensive Performance Report:")
    report = get_performance_report()
    print(report[:400] + "..." if len(report) > 400 else report)
    
    # Memory optimization suggestions
    print(f"\n💡 Memory Optimization Suggestions:")
    if total_memory_time > 1.0:
        print("  - Consider implementing memory caching strategies")
        print("  - Optimize vector search indexes for faster retrieval")
    if total_memory_ops > 10:
        print("  - Consider batching memory operations for efficiency")
    print("  - Monitor memory consolidation frequency vs performance")
    
    return {
        'conversation_turns': len(conversation_results),
        'memory_operations': total_memory_ops,
        'total_memory_time': total_memory_time
    }

if __name__ == "__main__":
    result = main()
    print(f"\n✅ Memory agent monitoring completed!")
    print(f"Processed {result['conversation_turns']} conversation turns")
    print(f"Executed {result['memory_operations']} memory operations in {result['total_memory_time']:.3f}s")