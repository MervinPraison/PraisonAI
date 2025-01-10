from praisonaiagents import Agent, Task, PraisonAIAgents
import logging
import os

def main():
    # Initialize memory config
    memory_config = {
        "provider": "rag",
        "use_embedding": True,
        "storage": {
            "type": "sqlite",
            "path": "./.praison/memory.db"
        },
        "rag_db_path": "./.praison/chroma_db"
    }
    
    # Test facts
    fact1 = "The capital city of Jujuha is Hahanu and its population is 102300"
    fact2 = "Three main ingredients in a classic proloder are eggs, sugar, and flour"
    fact3 = "The year the first Josinga was released is 2007"
    
    # # Check if database exists
    # if os.path.exists("./memory.db"):
    #     logger.info("Found existing memory database")
    # else:
    #     logger.info("Creating new memory database")
    
    # Create task config (without memory config since it's moved to PraisonAIAgents)
    task_config = {}

    # Create agents with different roles
    researcher = Agent(
        role="Research Analyst",
        goal="Research and document key information about topics",
        backstory="Expert at analyzing and storing information in memory",
        llm="gpt-4o-mini"
    )
    
    retriever = Agent(
        role="Information Retriever",
        goal="Retrieve and verify stored information from memory",
        backstory="Specialist in searching and validating information from memory",
        llm="gpt-4o-mini"
    )

    # Task 1: Process the facts
    store_task = Task(
        description=f"""
        Process and analyze this information:
        1. {fact1}
        2. {fact2}
        3. {fact3}

        Provide a clear summary of each fact.
        """,
        expected_output="""
        Clear statements summarizing each fact.
        Example format:
        1. [Summary of fact 1]
        2. [Summary of fact 2]
        3. [Summary of fact 3]
        """,
        agent=researcher
    )

    # Task 2: Write essay about AI
    verify_task = Task(
        description="""
        write few points about AI
        """,
        expected_output="Points about AI",
        agent=retriever
    )

    # Task 3: Query memory
    query_task = Task(
        description="""
        Using ONLY information found in memory:
        1. What is stored in memory about Hahanu?
        2. What ingredients for proloder are recorded in memory?
        3. What year is stored in memory for the Josinga release?

        For each answer, cite the memory record you found.
        """,
        expected_output="Answers based solely on memory records with citations",
        agent=retriever
    )

    # Task 4: Query both short-term and long-term memory
    query_both_task = Task(
        description="""
        Using ONLY information found in memory:
        1. What is stored in both short-term and long-term memory about Jujuha?
        2. What ingredients for proloder are recorded in both short-term and long-term memory?
        3. What year is stored in both short-term and long-term memory for the Josinga release?

        For each answer, cite the memory record you found.
        """,
        expected_output="Answers based solely on memory records with citations",
        agent=retriever
    )

    # Initialize PraisonAIAgents with memory configuration
    agents = PraisonAIAgents(
        agents=[researcher, retriever],
        tasks=[store_task, verify_task, query_task, query_both_task],
        verbose=True,  # Use same verbose level as memory
        memory=True,
        embedder={
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small"
            }
        }
    )

    # agents = PraisonAIAgents(
    #     agents=[researcher, retriever],
    #     tasks=[store_task, verify_task, query_task, query_both_task],
    #     verbose=True,  # Use same verbose level as memory
    #     memory=True
    # )
    
    # Execute tasks
    print("\nExecuting Memory Test Tasks...")
    print("-" * 50)
    agents.start()
    
    # Use shared memory for final checks
    memory = agents.shared_memory
    
    # Test memory retrieval with different quality thresholds
    if memory:
        print("\nFinal Memory Check:")
        print("-" * 50)
        
        queries = ["Jujuha", "proloder", "Josinga"]
        for query in queries:
            print(f"\nSearching memory for: {query}")
            
            # Search in both short-term and long-term memory
            print("\nShort-term memory results:")
            stm_results = memory.search_short_term(query)
            if stm_results:
                for item in stm_results:
                    print(f"Content: {item.get('content', '')[:200]}")
                    if 'meta' in item:
                        print(f"Metadata: {item['meta']}")
                    print("-" * 20)
            else:
                print("No results found in short-term memory")

            print("\nLong-term memory results:")
            ltm_results = memory.search_long_term(query)
            if ltm_results:
                for item in ltm_results:
                    print(f"Content: {item.get('text', '')[:200]}")
                    if 'metadata' in item:
                        print(f"Metadata: {item['metadata']}")
                    print("-" * 20)
            else:
                print("No results found in long-term memory")
                
            # Also check ChromaDB if using RAG
            if memory.use_rag and hasattr(memory, "chroma_col"):
                print("\nChromaDB results:")
                try:
                    all_items = memory.chroma_col.get()
                    print(f"Found {len(all_items['ids'])} items in ChromaDB")
                    for i in range(len(all_items['ids'])):
                        print(f"ID: {all_items['ids'][i]}")
                        print(f"Content: {all_items['documents'][i][:200]}")
                        print(f"Metadata: {all_items['metadatas'][i]}")
                        print("-" * 20)
                except Exception as e:
                    print(f"Error querying ChromaDB: {e}")
            
            print("-" * 30)
    else:
        print("\nNo memory available for final checks")

if __name__ == "__main__":
    main()
