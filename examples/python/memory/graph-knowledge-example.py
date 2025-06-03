#!/usr/bin/env python3
"""
Graph Knowledge Example

This example shows how to use graph memory with the Knowledge class
for enhanced document processing and relationship extraction.

Requirements:
    pip install "praisonaiagents[graph]"
"""

import os
from praisonaiagents.knowledge import Knowledge

def main():
    print("📚 Graph Knowledge Example")
    print("=" * 40)
    
    # Configuration with graph memory support
    config_with_graph = {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "graph_knowledge_test",
                "path": ".praison/graph_knowledge"
            }
        },
        "graph_store": {
            "provider": "memgraph",  # or "neo4j"
            "config": {
                "url": "bolt://localhost:7687",
                "username": "memgraph",
                "password": ""
            }
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": "gpt-4o-mini"
            }
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small"
            }
        },
        "reranker": {
            "enabled": True,
            "default_rerank": True
        }
    }
    
    # Fallback configuration (without graph store)
    config_basic = {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "basic_knowledge_test",
                "path": ".praison/basic_knowledge"
            }
        },
        "reranker": {
            "enabled": True,
            "default_rerank": True
        }
    }
    
    try:
        # Try graph-enabled knowledge first
        knowledge = Knowledge(config=config_with_graph, verbose=1)
        print("✅ Graph memory enabled!")
        graph_mode = True
    except Exception as e:
        print(f"⚠️  Graph memory not available: {e}")
        print("📦 Falling back to vector-only memory...")
        knowledge = Knowledge(config=config_basic, verbose=1)
        graph_mode = False
    
    # Sample documents with rich relationship information
    documents = [
        """
        OpenAI is an artificial intelligence research company founded in 2015. 
        The company was co-founded by Sam Altman, Greg Brockman, and Elon Musk, 
        among others. Sam Altman serves as the CEO, while Greg Brockman is the 
        President and Chairman. Elon Musk was initially involved but left the 
        board in 2018.
        """,
        """
        GPT-4 is OpenAI's most advanced language model, released in March 2023. 
        It powers ChatGPT Plus and is available through OpenAI's API. GPT-4 
        demonstrates improved reasoning and reduced hallucinations compared to 
        its predecessor GPT-3.5. The model uses transformer architecture and 
        was trained using reinforcement learning from human feedback (RLHF).
        """,
        """
        Microsoft has a significant partnership with OpenAI, having invested 
        billions of dollars in the company. This partnership allows Microsoft 
        to integrate OpenAI's models into products like Microsoft Copilot, 
        which is built into Office 365 and Windows. The collaboration gives 
        Microsoft exclusive access to GPT models for certain use cases.
        """,
        """
        Anthropic is a major competitor to OpenAI, founded by former OpenAI 
        researchers including Dario Amodei and Daniela Amodei. Anthropic 
        created Claude, an AI assistant that competes with ChatGPT. The company 
        focuses on AI safety research and constitutional AI training methods.
        """
    ]
    
    print(f"\n📥 Adding {len(documents)} documents to knowledge base...")
    
    # Add documents to knowledge base
    for i, doc in enumerate(documents, 1):
        try:
            result = knowledge.add(doc, user_id="demo_user")
            print(f"✓ Document {i} added successfully")
            if graph_mode:
                print(f"  Graph relationships extracted and stored")
        except Exception as e:
            print(f"❌ Error adding document {i}: {e}")
    
    print("\n🔍 Testing relationship-aware queries...")
    
    # Test queries that benefit from graph relationships
    queries = [
        "Who founded OpenAI?",
        "What is the relationship between OpenAI and Microsoft?",
        "How does GPT-4 compare to other models?",
        "Who are OpenAI's competitors?",
        "What role does Sam Altman play at OpenAI?",
        "How is Anthropic related to OpenAI?"
    ]
    
    for query in queries:
        print(f"\n❓ Query: {query}")
        try:
            results = knowledge.search(query, user_id="demo_user", limit=2)
            
            if results and hasattr(results, '__iter__'):
                for i, result in enumerate(results, 1):
                    if hasattr(result, 'get'):
                        content = result.get('memory', result.get('text', str(result)))
                    else:
                        content = str(result)
                    
                    # Truncate long responses
                    if len(content) > 200:
                        content = content[:197] + "..."
                    
                    print(f"  {i}. {content}")
            else:
                print("  No results found")
                
        except Exception as e:
            print(f"  ❌ Search error: {e}")
    
    print(f"\n{'✅ Graph Knowledge Example Complete!' if graph_mode else '✅ Basic Knowledge Example Complete!'}")
    print("=" * 40)
    
    if graph_mode:
        print("🧠 Graph memory successfully captured entity relationships!")
        print("   Queries benefit from understanding connections between entities.")
    else:
        print("📦 Vector memory provided semantic search capabilities.")
        print("💡 To enable graph memory, set up Neo4j or Memgraph and install:")
        print("   pip install \"mem0ai[graph]\"")

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set.")
        print("   Export your key: export OPENAI_API_KEY='your-key-here'")
        print("   Some features may not work without it.\n")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Example interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure you have the required dependencies installed:")
        print("   pip install \"praisonaiagents[graph]\"")