"""
Advanced Memory Search and Optimization Example

This example demonstrates sophisticated memory search patterns including semantic search,
memory quality optimization, multi-modal integration, and contextual filtering.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import uuid
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search, read_file

print("=== Advanced Memory Search and Optimization Example ===\n")

# Advanced Memory Search Classes
class SemanticMemorySearch:
    """Advanced semantic search with ranking and filtering"""
    
    def __init__(self):
        self.memory_index = {}
        self.search_history = []
        self.relevance_threshold = 0.7
        self.search_analytics = {
            "total_searches": 0,
            "successful_searches": 0,
            "avg_results_returned": 0
        }
    
    def add_memory(self, memory_id: str, content: str, metadata: Dict[str, Any]):
        """Add memory with rich metadata for enhanced search"""
        self.memory_index[memory_id] = {
            "content": content,
            "metadata": metadata,
            "created_at": datetime.now().isoformat(),
            "access_count": 0,
            "last_accessed": None,
            "relevance_scores": {},
            "quality_score": self._calculate_quality_score(content, metadata)
        }
    
    def _calculate_quality_score(self, content: str, metadata: Dict[str, Any]) -> float:
        """Calculate memory quality score based on content and metadata"""
        score = 0.5  # Base score
        
        # Content quality factors
        if len(content) > 100:
            score += 0.1
        if len(content.split()) > 50:
            score += 0.1
        
        # Metadata richness
        if metadata.get("source"):
            score += 0.1
        if metadata.get("verified", False):
            score += 0.2
        if metadata.get("importance", 0) > 0.7:
            score += 0.1
        
        return min(1.0, score)
    
    def semantic_search(
        self, 
        query: str, 
        filters: Dict[str, Any] = None,
        max_results: int = 10,
        boost_recent: bool = True,
        include_similar: bool = True
    ) -> List[Dict[str, Any]]:
        """Advanced semantic search with filtering and ranking"""
        
        self.search_analytics["total_searches"] += 1
        
        # Log search
        search_record = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "filters": filters,
            "search_id": str(uuid.uuid4())
        }
        self.search_history.append(search_record)
        
        results = []
        
        for memory_id, memory in self.memory_index.items():
            # Basic relevance scoring (simplified semantic matching)
            relevance_score = self._calculate_relevance(query, memory["content"])
            
            # Apply filters
            if filters and not self._passes_filters(memory, filters):
                continue
            
            # Boost recent memories if requested
            if boost_recent:
                recency_boost = self._calculate_recency_boost(memory["created_at"])
                relevance_score *= recency_boost
            
            # Quality boost
            relevance_score *= (0.5 + memory["quality_score"] * 0.5)
            
            if relevance_score >= self.relevance_threshold:
                results.append({
                    "memory_id": memory_id,
                    "content": memory["content"],
                    "metadata": memory["metadata"],
                    "relevance_score": relevance_score,
                    "quality_score": memory["quality_score"],
                    "access_count": memory["access_count"]
                })
                
                # Update access tracking
                self.memory_index[memory_id]["access_count"] += 1
                self.memory_index[memory_id]["last_accessed"] = datetime.now().isoformat()
        
        # Sort by relevance score
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        # Update analytics
        if results:
            self.search_analytics["successful_searches"] += 1
        
        result_count = min(len(results), max_results)
        self.search_analytics["avg_results_returned"] = (
            (self.search_analytics["avg_results_returned"] * (self.search_analytics["total_searches"] - 1) + result_count) /
            self.search_analytics["total_searches"]
        )
        
        return results[:max_results]
    
    def _calculate_relevance(self, query: str, content: str) -> float:
        """Calculate relevance score between query and content"""
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        
        # Simple overlap scoring (in production, use embeddings)
        if not query_words:
            return 0.0
        
        overlap = len(query_words.intersection(content_words))
        return overlap / len(query_words)
    
    def _passes_filters(self, memory: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if memory passes filter criteria"""
        for filter_key, filter_value in filters.items():
            if filter_key == "min_quality":
                if memory["quality_score"] < filter_value:
                    return False
            elif filter_key == "source":
                if memory["metadata"].get("source") != filter_value:
                    return False
            elif filter_key == "date_range":
                memory_date = datetime.fromisoformat(memory["created_at"])
                if not (filter_value["start"] <= memory_date <= filter_value["end"]):
                    return False
            elif filter_key == "tags":
                memory_tags = set(memory["metadata"].get("tags", []))
                required_tags = set(filter_value)
                if not required_tags.issubset(memory_tags):
                    return False
        
        return True
    
    def _calculate_recency_boost(self, created_at: str) -> float:
        """Calculate boost factor based on memory recency"""
        created_date = datetime.fromisoformat(created_at)
        age_days = (datetime.now() - created_date).days
        
        if age_days == 0:
            return 1.2  # Today's memories get boost
        elif age_days <= 7:
            return 1.1  # This week's memories get small boost
        elif age_days <= 30:
            return 1.0  # This month's memories - no boost
        else:
            return 0.9  # Older memories get slight penalty
    
    def optimize_memory_index(self):
        """Optimize memory index by removing low-quality, unused memories"""
        current_time = datetime.now()
        optimization_stats = {
            "memories_before": len(self.memory_index),
            "removed_low_quality": 0,
            "removed_unused": 0,
            "memories_after": 0
        }
        
        memories_to_remove = []
        
        for memory_id, memory in self.memory_index.items():
            # Remove very low quality memories that haven't been accessed
            if memory["quality_score"] < 0.3 and memory["access_count"] == 0:
                memories_to_remove.append(memory_id)
                optimization_stats["removed_low_quality"] += 1
                continue
            
            # Remove old, unused memories
            if memory["access_count"] == 0:
                created_date = datetime.fromisoformat(memory["created_at"])
                if (current_time - created_date).days > 90:  # 90 days old and never accessed
                    memories_to_remove.append(memory_id)
                    optimization_stats["removed_unused"] += 1
        
        # Remove flagged memories
        for memory_id in memories_to_remove:
            del self.memory_index[memory_id]
        
        optimization_stats["memories_after"] = len(self.memory_index)
        return optimization_stats

class ContextualMemoryFilter:
    """Context-aware memory filtering and ranking"""
    
    def __init__(self):
        self.context_history = []
        self.context_weights = {
            "current_task": 0.4,
            "recent_tasks": 0.3,
            "user_preferences": 0.2,
            "domain_expertise": 0.1
        }
    
    def update_context(self, context_type: str, context_data: Dict[str, Any]):
        """Update current context for memory filtering"""
        self.context_history.append({
            "type": context_type,
            "data": context_data,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only recent context (last 10 entries)
        if len(self.context_history) > 10:
            self.context_history = self.context_history[-10:]
    
    def filter_by_context(
        self, 
        memories: List[Dict[str, Any]], 
        current_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Filter and rerank memories based on current context"""
        
        contextual_memories = []
        
        for memory in memories:
            context_relevance = self._calculate_context_relevance(
                memory, current_context
            )
            
            # Adjust relevance score based on context
            adjusted_score = (
                memory["relevance_score"] * 0.7 + 
                context_relevance * 0.3
            )
            
            memory_copy = memory.copy()
            memory_copy["context_relevance"] = context_relevance
            memory_copy["adjusted_relevance"] = adjusted_score
            contextual_memories.append(memory_copy)
        
        # Re-sort by adjusted relevance
        contextual_memories.sort(key=lambda x: x["adjusted_relevance"], reverse=True)
        
        return contextual_memories
    
    def _calculate_context_relevance(
        self, 
        memory: Dict[str, Any], 
        current_context: Dict[str, Any]
    ) -> float:
        """Calculate how relevant memory is to current context"""
        relevance = 0.0
        
        # Current task relevance
        current_task = current_context.get("task_type")
        memory_task_type = memory["metadata"].get("task_type")
        if current_task and memory_task_type == current_task:
            relevance += self.context_weights["current_task"]
        
        # Domain expertise relevance
        current_domain = current_context.get("domain")
        memory_domain = memory["metadata"].get("domain")
        if current_domain and memory_domain == current_domain:
            relevance += self.context_weights["domain_expertise"]
        
        # User preferences
        user_preferences = current_context.get("user_preferences", {})
        memory_tags = memory["metadata"].get("tags", [])
        preferred_tags = user_preferences.get("preferred_topics", [])
        
        if preferred_tags and memory_tags:
            tag_overlap = len(set(preferred_tags).intersection(set(memory_tags)))
            if tag_overlap > 0:
                relevance += self.context_weights["user_preferences"] * (tag_overlap / len(preferred_tags))
        
        return min(1.0, relevance)

class MultiModalMemoryIntegration:
    """Integration layer for multi-modal memory (text, images, audio)"""
    
    def __init__(self):
        self.modality_weights = {
            "text": 1.0,
            "image": 0.8,
            "audio": 0.6,
            "structured_data": 0.9
        }
        self.cross_modal_mappings = {}
    
    def add_cross_modal_memory(
        self, 
        memory_id: str, 
        modalities: Dict[str, Any],
        relationships: List[Dict[str, str]] = None
    ):
        """Add memory that spans multiple modalities"""
        self.cross_modal_mappings[memory_id] = {
            "modalities": modalities,
            "relationships": relationships or [],
            "created_at": datetime.now().isoformat()
        }
    
    def search_across_modalities(
        self, 
        query: str, 
        target_modality: str = "text",
        include_related: bool = True
    ) -> List[Dict[str, Any]]:
        """Search across different modalities with cross-modal relevance"""
        results = []
        
        for memory_id, memory in self.cross_modal_mappings.items():
            modalities = memory["modalities"]
            
            # Calculate relevance for target modality
            if target_modality in modalities:
                relevance = self._calculate_modality_relevance(
                    query, modalities[target_modality], target_modality
                )
                
                # Boost score if multiple modalities are present
                modality_count = len(modalities)
                multi_modal_boost = 1.0 + (modality_count - 1) * 0.1
                
                results.append({
                    "memory_id": memory_id,
                    "primary_modality": target_modality,
                    "content": modalities[target_modality],
                    "all_modalities": list(modalities.keys()),
                    "relevance_score": relevance * multi_modal_boost,
                    "multi_modal_boost": multi_modal_boost
                })
        
        # Sort by relevance
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return results
    
    def _calculate_modality_relevance(
        self, 
        query: str, 
        content: Any, 
        modality: str
    ) -> float:
        """Calculate relevance for specific modality"""
        if modality == "text":
            # Text similarity (simplified)
            query_words = set(query.lower().split())
            content_words = set(str(content).lower().split())
            if query_words:
                overlap = len(query_words.intersection(content_words))
                return overlap / len(query_words)
        
        elif modality == "structured_data":
            # Check if query terms match data fields or values
            if isinstance(content, dict):
                content_str = json.dumps(content).lower()
                return len([word for word in query.lower().split() if word in content_str]) / len(query.split())
        
        return 0.5  # Default relevance for other modalities

# Example 1: Semantic Memory Search with Rich Metadata
print("Example 1: Advanced Semantic Search")
print("-" * 40)

# Initialize semantic search system
semantic_search = SemanticMemorySearch()

# Add memories with rich metadata
semantic_search.add_memory(
    "research_001",
    "Artificial intelligence market size reached $150 billion in 2023 with 25% year-over-year growth. Major drivers include enterprise AI adoption and generative AI applications.",
    {
        "source": "Market Research Report 2024",
        "verified": True,
        "importance": 0.9,
        "tags": ["ai", "market", "growth", "enterprise"],
        "domain": "technology",
        "task_type": "market_research"
    }
)

semantic_search.add_memory(
    "tech_trends_001", 
    "Cloud computing adoption continues to accelerate with 70% of enterprises migrating workloads to cloud platforms. Hybrid cloud solutions dominate the landscape.",
    {
        "source": "Tech Industry Analysis",
        "verified": True,
        "importance": 0.8,
        "tags": ["cloud", "enterprise", "migration", "hybrid"],
        "domain": "technology",
        "task_type": "trend_analysis"
    }
)

semantic_search.add_memory(
    "startup_data_001",
    "AI startups raised $25 billion in funding in 2023, with computer vision and NLP companies receiving the largest investments.",
    {
        "source": "Venture Capital Database",
        "verified": False,
        "importance": 0.7,
        "tags": ["ai", "startups", "funding", "computer_vision", "nlp"],
        "domain": "finance",
        "task_type": "investment_analysis"
    }
)

# Perform semantic searches
print("Search 1: AI market growth")
results_1 = semantic_search.semantic_search(
    "AI market growth trends",
    filters={"min_quality": 0.7, "tags": ["ai"]},
    max_results=5,
    boost_recent=True
)

for result in results_1:
    print(f"  Memory ID: {result['memory_id']}")
    print(f"  Relevance: {result['relevance_score']:.2f}")
    print(f"  Quality: {result['quality_score']:.2f}")
    print(f"  Content: {result['content'][:100]}...")
    print()

# Example 2: Contextual Memory Filtering
print("Example 2: Context-Aware Memory Filtering")
print("-" * 40)

contextual_filter = ContextualMemoryFilter()

# Update context based on current task
current_context = {
    "task_type": "market_research",
    "domain": "technology", 
    "user_preferences": {
        "preferred_topics": ["ai", "market", "growth"]
    }
}

contextual_filter.update_context("current_task", current_context)

# Filter previous results by context
contextual_results = contextual_filter.filter_by_context(results_1, current_context)

print("Context-filtered results:")
for result in contextual_results:
    print(f"  Memory ID: {result['memory_id']}")
    print(f"  Original Relevance: {result['relevance_score']:.2f}")
    print(f"  Context Relevance: {result['context_relevance']:.2f}")
    print(f"  Adjusted Relevance: {result['adjusted_relevance']:.2f}")
    print()

# Example 3: Multi-Modal Memory Integration
print("Example 3: Multi-Modal Memory Search")
print("-" * 40)

multi_modal = MultiModalMemoryIntegration()

# Add multi-modal memory
multi_modal.add_cross_modal_memory(
    "product_analysis_001",
    {
        "text": "iPhone 15 Pro features advanced A17 Pro chip with improved performance and camera capabilities",
        "structured_data": {
            "product": "iPhone 15 Pro",
            "chip": "A17 Pro",
            "features": ["performance", "camera", "titanium"],
            "price": 999,
            "rating": 4.5
        },
        "image": "product_image_url_placeholder"
    },
    relationships=[
        {"type": "describes", "source": "text", "target": "structured_data"},
        {"type": "illustrates", "source": "image", "target": "text"}
    ]
)

# Search across modalities
multi_modal_results = multi_modal.search_across_modalities(
    "iPhone performance features",
    target_modality="text",
    include_related=True
)

print("Multi-modal search results:")
for result in multi_modal_results:
    print(f"  Memory ID: {result['memory_id']}")
    print(f"  Primary Modality: {result['primary_modality']}")
    print(f"  Available Modalities: {result['all_modalities']}")
    print(f"  Relevance Score: {result['relevance_score']:.2f}")
    print(f"  Multi-modal Boost: {result['multi_modal_boost']:.2f}")
    print()

# Example 4: Memory Quality Optimization
print("Example 4: Memory Optimization")
print("-" * 40)

# Add some low-quality memories for optimization demo
semantic_search.add_memory(
    "poor_quality_001",
    "Bad data here",
    {
        "source": None,
        "verified": False,
        "importance": 0.1,
        "tags": [],
        "domain": "unknown"
    }
)

print("Before optimization:")
print(f"Total memories: {len(semantic_search.memory_index)}")

# Optimize memory index
optimization_stats = semantic_search.optimize_memory_index()

print("\nOptimization results:")
print(f"Memories before: {optimization_stats['memories_before']}")
print(f"Removed low quality: {optimization_stats['removed_low_quality']}")
print(f"Removed unused: {optimization_stats['removed_unused']}")
print(f"Memories after: {optimization_stats['memories_after']}")

# Example 5: Memory Search Analytics
print("\nExample 5: Search Analytics")
print("-" * 40)

analytics = semantic_search.search_analytics
print(f"Total searches performed: {analytics['total_searches']}")
print(f"Successful searches: {analytics['successful_searches']}")
print(f"Search success rate: {analytics['successful_searches']/analytics['total_searches']:.1%}")
print(f"Average results per search: {analytics['avg_results_returned']:.1f}")

# Search history analysis
print(f"\nSearch history (last 3 searches):")
for search in semantic_search.search_history[-3:]:
    print(f"  Query: '{search['query']}'")
    print(f"  Timestamp: {search['timestamp']}")
    print(f"  Filters: {search['filters']}")

print(f"\n=== Memory Search Optimization Summary ===")
print(f"✅ Semantic search with quality scoring")
print(f"✅ Contextual filtering and ranking")
print(f"✅ Multi-modal memory integration")
print(f"✅ Memory index optimization")
print(f"✅ Search analytics and monitoring")
print(f"📊 System efficiency: {analytics['successful_searches']/analytics['total_searches']:.1%} success rate")

print("\nAdvanced memory search optimization example complete!")