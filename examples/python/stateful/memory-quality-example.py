#!/usr/bin/env python3
"""
Memory Quality Management Example

Demonstrates advanced memory management with quality scoring,
filtering, and multi-tiered storage strategies.
"""

from praisonaiagents import Agent, Memory

def main():
    print("🧠 Memory Quality Management Example")
    print("=" * 50)
    
    # Initialize memory with quality-based configuration
    memory_config = {
        "provider": "rag",
        "use_embedding": True,
        "rag_db_path": "quality_memory_db"
    }
    
    memory = Memory(config=memory_config, verbose=5)
    print(f"📦 Initialized memory system with provider: {memory_config['provider']}")
    
    # Create agent with memory
    agent = Agent(
        name="Knowledge Manager",
        role="Information Quality Specialist",
        instructions="Store and retrieve information with quality assessment",
        memory=memory,
        user_id="quality_demo_user"
    )
    
    print(f"🤖 Created agent: {agent.name}")
    
    # Store information with different quality levels
    print("\n📝 Storing information with quality metrics...")
    
    # High quality information
    memory.store_long_term(
        text="Artificial Intelligence safety research focuses on ensuring AI systems remain beneficial and controllable as they become more capable. Key areas include alignment, robustness, and interpretability.",
        metadata={"source": "research_paper", "domain": "ai_safety"},
        completeness=0.95,
        relevance=0.90,
        clarity=0.88,
        accuracy=0.92
    )
    
    # Medium quality information  
    memory.store_long_term(
        text="Machine learning models can sometimes behave unexpectedly in production environments.",
        metadata={"source": "blog_post", "domain": "ml_engineering"},
        completeness=0.60,
        relevance=0.75,
        clarity=0.70,
        accuracy=0.65
    )
    
    # Low quality information
    memory.store_long_term(
        text="AI is really cool and might change everything in the future maybe.",
        metadata={"source": "social_media", "domain": "general"},
        completeness=0.30,
        relevance=0.40,
        clarity=0.35,
        accuracy=0.25
    )
    
    # Store with external quality score
    memory.store_long_term(
        text="Recent advances in transformer architectures have led to significant improvements in natural language understanding tasks, with models achieving state-of-the-art performance on multiple benchmarks.",
        metadata={"source": "academic_conference", "domain": "nlp"},
        evaluator_quality=0.88
    )
    
    print("✅ Stored 4 pieces of information with varying quality levels")
    
    # Search with different quality thresholds
    print("\n🔍 Searching with quality filters...")
    
    query = "artificial intelligence safety"
    
    # High quality search (0.8+ quality)
    high_quality = memory.search_long_term(
        query=query,
        min_quality=0.8,
        limit=10
    )
    
    print(f"\n🏆 High quality results (0.8+): {len(high_quality)} found")
    for i, result in enumerate(high_quality, 1):
        quality = result.get('metadata', {}).get('quality', 0.0)
        text_preview = result.get('text', '')[:100] + "..."
        print(f"  {i}. Quality: {quality:.2f} - {text_preview}")
    
    # Medium quality search (0.6+ quality)  
    medium_quality = memory.search_long_term(
        query=query,
        min_quality=0.6,
        limit=10
    )
    
    print(f"\n📊 Medium quality results (0.6+): {len(medium_quality)} found")
    for i, result in enumerate(medium_quality, 1):
        quality = result.get('metadata', {}).get('quality', 0.0)
        source = result.get('metadata', {}).get('source', 'unknown')
        print(f"  {i}. Quality: {quality:.2f}, Source: {source}")
    
    # All results (no quality filter)
    all_results = memory.search_long_term(
        query=query,
        min_quality=0.0,
        limit=10
    )
    
    print(f"\n📚 All results (no filter): {len(all_results)} found")
    
    # Demonstrate quality calculation
    print("\n🧮 Quality Score Calculation Demo:")
    
    # Calculate quality with custom weights
    custom_weights = {
        "completeness": 0.3,
        "relevance": 0.4, 
        "clarity": 0.2,
        "accuracy": 0.1
    }
    
    quality_score = memory.compute_quality_score(
        completeness=0.85,
        relevance=0.90,
        clarity=0.75,
        accuracy=0.95,
        weights=custom_weights
    )
    
    print(f"Custom quality score: {quality_score}")
    
    # Store information with calculated quality
    memory.store_long_term(
        text="Reinforcement learning from human feedback (RLHF) has emerged as a crucial technique for aligning large language models with human preferences and values.",
        metadata={"source": "research_review", "domain": "ai_alignment"},
        completeness=0.85,
        relevance=0.90, 
        clarity=0.75,
        accuracy=0.95,
        weights=custom_weights
    )
    
    print("✅ Stored information with custom quality calculation")
    
    # Demonstrate agent conversation with quality-aware memory
    print("\n💬 Agent conversation with quality-aware memory retrieval...")
    
    response1 = agent.chat("What do you know about AI safety? Please prioritize high-quality information.")
    print(f"Agent: {response1}")
    
    # Store the conversation with quality assessment
    memory.store_short_term(
        text="User asked about AI safety. Agent provided response based on high-quality sources.",
        metadata={
            "interaction_type": "qa",
            "topic": "ai_safety", 
            "quality_preference": "high"
        },
        evaluator_quality=0.75  # Conversational quality
    )
    
    # Search conversation history
    print("\n📖 Searching conversation history...")
    conversation_history = memory.search_short_term(
        query="ai safety interaction",
        min_quality=0.5,
        limit=5
    )
    
    print(f"Found {len(conversation_history)} relevant conversation entries")
    
    # Demonstrate context building with quality filtering
    print("\n🧩 Building context with quality filters...")
    
    context = memory.build_context_for_task(
        task_descr="Explain AI alignment challenges",
        user_id="quality_demo_user",
        max_items=3
    )
    
    if context:
        print("Generated context preview:")
        print(context[:300] + "..." if len(context) > 300 else context)
    
    # Final agent interaction using built context
    print("\n🎯 Final interaction with quality-filtered context...")
    
    response2 = agent.chat("Can you elaborate on alignment challenges in AI systems?")
    print(f"Agent: {response2}")
    
    # Display memory statistics
    print("\n📊 Memory System Statistics:")
    print("=" * 30)
    
    # Search for all stored items
    all_ltm = memory.search_long_term("", limit=100)  # Empty query to get all
    all_stm = memory.search_short_term("", limit=100)
    
    quality_distribution = {"high": 0, "medium": 0, "low": 0}
    
    for item in all_ltm:
        quality = item.get('metadata', {}).get('quality', 0.0)
        if quality >= 0.8:
            quality_distribution["high"] += 1
        elif quality >= 0.6:
            quality_distribution["medium"] += 1
        else:
            quality_distribution["low"] += 1
    
    print(f"Long-term memory items: {len(all_ltm)}")
    print(f"Short-term memory items: {len(all_stm)}")
    print(f"Quality distribution: {quality_distribution}")
    
    print("\n✅ Memory quality management example completed!")
    print("The system demonstrated quality-based storage, retrieval, and filtering.")

if __name__ == "__main__":
    main()