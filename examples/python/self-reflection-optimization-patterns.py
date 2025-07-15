"""
Self-Reflection Optimization Patterns Example

This example demonstrates advanced self-reflection capabilities including adaptive strategies,
quality-based termination, multi-agent reflection coordination, and performance optimization.
"""

import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Self-Reflection Optimization Patterns Example ===\n")

# Advanced Self-Reflection Classes
class ReflectionStrategy:
    """Adaptive reflection strategy manager"""
    
    def __init__(self):
        self.strategies = {
            "quality_focused": {
                "max_iterations": 5,
                "quality_threshold": 0.8,
                "improvement_threshold": 0.1,
                "focus_areas": ["accuracy", "completeness", "clarity"]
            },
            "efficiency_focused": {
                "max_iterations": 3,
                "quality_threshold": 0.7,
                "improvement_threshold": 0.05,
                "focus_areas": ["conciseness", "relevance"]
            },
            "creativity_focused": {
                "max_iterations": 7,
                "quality_threshold": 0.75,
                "improvement_threshold": 0.15,
                "focus_areas": ["originality", "innovation", "creativity"]
            },
            "balanced": {
                "max_iterations": 4,
                "quality_threshold": 0.75,
                "improvement_threshold": 0.08,
                "focus_areas": ["accuracy", "clarity", "relevance"]
            }
        }
        self.current_strategy = "balanced"
        self.adaptation_history = []
    
    def select_strategy(self, task_type: str, context: Dict[str, Any]) -> str:
        """Intelligently select reflection strategy based on task and context"""
        
        # Strategy selection logic
        if task_type in ["research", "analysis", "fact_checking"]:
            strategy = "quality_focused"
        elif task_type in ["summary", "brief", "quick_response"]:
            strategy = "efficiency_focused"
        elif task_type in ["writing", "brainstorming", "design"]:
            strategy = "creativity_focused"
        else:
            strategy = "balanced"
        
        # Consider urgency
        if context.get("urgency", "normal") == "high":
            if strategy == "quality_focused":
                strategy = "balanced"
            elif strategy == "creativity_focused":
                strategy = "balanced"
        
        # Consider quality requirements
        if context.get("quality_requirement", "normal") == "high":
            if strategy == "efficiency_focused":
                strategy = "quality_focused"
        
        self.current_strategy = strategy
        
        # Log strategy selection
        self.adaptation_history.append({
            "timestamp": datetime.now().isoformat(),
            "task_type": task_type,
            "context": context,
            "selected_strategy": strategy,
            "reason": "adaptive_selection"
        })
        
        return strategy
    
    def get_strategy_config(self, strategy_name: str = None) -> Dict[str, Any]:
        """Get configuration for specified or current strategy"""
        strategy = strategy_name or self.current_strategy
        return self.strategies.get(strategy, self.strategies["balanced"])
    
    def adapt_strategy(self, performance_metrics: Dict[str, Any]):
        """Adapt strategy based on performance feedback"""
        current_config = self.get_strategy_config()
        
        # Analyze performance
        if performance_metrics.get("iterations_used", 0) >= current_config["max_iterations"]:
            if performance_metrics.get("final_quality", 0) < current_config["quality_threshold"]:
                # Switch to quality-focused strategy
                self.current_strategy = "quality_focused"
                adaptation_reason = "insufficient_quality_with_max_iterations"
            else:
                # Strategy worked well
                adaptation_reason = "strategy_effective"
        
        elif performance_metrics.get("improvement_rate", 0) < current_config["improvement_threshold"]:
            # Low improvement rate, try efficiency focused
            self.current_strategy = "efficiency_focused"
            adaptation_reason = "low_improvement_rate"
        
        else:
            adaptation_reason = "no_adaptation_needed"
        
        # Log adaptation
        self.adaptation_history.append({
            "timestamp": datetime.now().isoformat(),
            "performance_metrics": performance_metrics,
            "old_strategy": self.current_strategy,
            "new_strategy": self.current_strategy,
            "reason": adaptation_reason
        })

class QualityAssessment:
    """Advanced quality assessment for reflection termination"""
    
    def __init__(self):
        self.assessment_criteria = {
            "accuracy": {"weight": 0.3, "evaluator": self._assess_accuracy},
            "completeness": {"weight": 0.25, "evaluator": self._assess_completeness},
            "clarity": {"weight": 0.2, "evaluator": self._assess_clarity},
            "relevance": {"weight": 0.15, "evaluator": self._assess_relevance},
            "originality": {"weight": 0.1, "evaluator": self._assess_originality}
        }
        self.quality_history = []
    
    def assess_quality(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive quality assessment"""
        scores = {}
        weighted_score = 0.0
        
        for criterion, config in self.assessment_criteria.items():
            score = config["evaluator"](content, context)
            scores[criterion] = score
            weighted_score += score * config["weight"]
        
        assessment = {
            "overall_score": weighted_score,
            "criterion_scores": scores,
            "assessment_timestamp": datetime.now().isoformat(),
            "content_length": len(content),
            "word_count": len(content.split())
        }
        
        self.quality_history.append(assessment)
        return assessment
    
    def _assess_accuracy(self, content: str, context: Dict[str, Any]) -> float:
        """Assess factual accuracy (simplified heuristic)"""
        # Check for fact-indicating phrases
        accuracy_indicators = [
            "according to", "research shows", "studies indicate",
            "data reveals", "statistics show", "evidence suggests"
        ]
        
        indicator_count = sum(1 for indicator in accuracy_indicators if indicator in content.lower())
        
        # Penalty for unsupported claims
        claim_words = ["definitely", "certainly", "always", "never", "all", "none"]
        unsupported_claims = sum(1 for word in claim_words if word in content.lower())
        
        base_score = 0.7  # Default accuracy
        accuracy_boost = min(0.3, indicator_count * 0.1)
        accuracy_penalty = min(0.4, unsupported_claims * 0.1)
        
        return max(0.0, min(1.0, base_score + accuracy_boost - accuracy_penalty))
    
    def _assess_completeness(self, content: str, context: Dict[str, Any]) -> float:
        """Assess content completeness"""
        expected_length = context.get("expected_word_count", 200)
        actual_length = len(content.split())
        
        # Assess based on length relative to expectation
        if actual_length >= expected_length * 0.8:
            length_score = 1.0
        elif actual_length >= expected_length * 0.6:
            length_score = 0.8
        elif actual_length >= expected_length * 0.4:
            length_score = 0.6
        else:
            length_score = 0.4
        
        # Check for key elements if specified
        required_elements = context.get("required_elements", [])
        if required_elements:
            element_coverage = sum(1 for element in required_elements 
                                 if element.lower() in content.lower()) / len(required_elements)
        else:
            element_coverage = 1.0
        
        return (length_score + element_coverage) / 2
    
    def _assess_clarity(self, content: str, context: Dict[str, Any]) -> float:
        """Assess content clarity"""
        sentences = content.split('.')
        
        # Average sentence length (clarity decreases with very long sentences)
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
        
        if avg_sentence_length <= 15:
            clarity_score = 1.0
        elif avg_sentence_length <= 20:
            clarity_score = 0.8
        elif avg_sentence_length <= 25:
            clarity_score = 0.6
        else:
            clarity_score = 0.4
        
        # Check for transition words (improves clarity)
        transition_words = ["however", "therefore", "furthermore", "moreover", "additionally", "consequently"]
        transition_count = sum(1 for word in transition_words if word in content.lower())
        transition_boost = min(0.2, transition_count * 0.05)
        
        return min(1.0, clarity_score + transition_boost)
    
    def _assess_relevance(self, content: str, context: Dict[str, Any]) -> float:
        """Assess content relevance to task"""
        task_keywords = context.get("task_keywords", [])
        if not task_keywords:
            return 0.8  # Default if no keywords provided
        
        content_lower = content.lower()
        keyword_matches = sum(1 for keyword in task_keywords if keyword.lower() in content_lower)
        
        return min(1.0, keyword_matches / len(task_keywords))
    
    def _assess_originality(self, content: str, context: Dict[str, Any]) -> float:
        """Assess content originality"""
        # Simple heuristic: check for common phrases vs unique expressions
        common_phrases = [
            "in conclusion", "to summarize", "it is important to note",
            "there are many", "it is clear that", "one of the most"
        ]
        
        common_phrase_count = sum(1 for phrase in common_phrases if phrase in content.lower())
        
        # More common phrases = lower originality
        originality_score = max(0.3, 1.0 - (common_phrase_count * 0.2))
        
        return originality_score
    
    def should_continue_reflection(self, assessment: Dict[str, Any], strategy_config: Dict[str, Any]) -> bool:
        """Determine if reflection should continue based on quality assessment"""
        current_quality = assessment["overall_score"]
        quality_threshold = strategy_config["quality_threshold"]
        
        # Check if quality threshold is met
        if current_quality >= quality_threshold:
            return False
        
        # Check improvement rate if we have previous assessments
        if len(self.quality_history) >= 2:
            previous_quality = self.quality_history[-2]["overall_score"]
            improvement = current_quality - previous_quality
            improvement_threshold = strategy_config["improvement_threshold"]
            
            if improvement < improvement_threshold:
                return False  # Minimal improvement, stop reflecting
        
        return True

class ReflectionCoordinator:
    """Coordinate reflection across multiple agents"""
    
    def __init__(self):
        self.agent_reflections = {}
        self.coordination_history = []
        self.consensus_threshold = 0.8
    
    def add_agent_reflection(self, agent_name: str, reflection_data: Dict[str, Any]):
        """Add reflection from an agent"""
        if agent_name not in self.agent_reflections:
            self.agent_reflections[agent_name] = []
        
        self.agent_reflections[agent_name].append({
            "reflection": reflection_data,
            "timestamp": datetime.now().isoformat()
        })
    
    def coordinate_reflections(self, task_id: str) -> Dict[str, Any]:
        """Coordinate reflections from multiple agents"""
        coordination_result = {
            "task_id": task_id,
            "participating_agents": list(self.agent_reflections.keys()),
            "consensus_achieved": False,
            "final_recommendations": [],
            "coordination_timestamp": datetime.now().isoformat()
        }
        
        if not self.agent_reflections:
            return coordination_result
        
        # Analyze reflection patterns
        all_suggestions = []
        quality_scores = []
        
        for agent_name, reflections in self.agent_reflections.items():
            if reflections:
                latest_reflection = reflections[-1]["reflection"]
                all_suggestions.extend(latest_reflection.get("suggestions", []))
                quality_scores.append(latest_reflection.get("quality_score", 0.5))
        
        # Find common suggestions (simplified consensus)
        suggestion_counts = {}
        for suggestion in all_suggestions:
            suggestion_key = suggestion.lower().strip()
            suggestion_counts[suggestion_key] = suggestion_counts.get(suggestion_key, 0) + 1
        
        # Identify consensus items
        agent_count = len(self.agent_reflections)
        consensus_suggestions = []
        
        for suggestion, count in suggestion_counts.items():
            if count / agent_count >= self.consensus_threshold:
                consensus_suggestions.append({
                    "suggestion": suggestion,
                    "agreement_rate": count / agent_count,
                    "priority": "high"
                })
        
        coordination_result["consensus_achieved"] = len(consensus_suggestions) > 0
        coordination_result["final_recommendations"] = consensus_suggestions
        coordination_result["average_quality"] = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        # Log coordination
        self.coordination_history.append(coordination_result)
        
        return coordination_result

# Example 1: Adaptive Reflection Strategy
print("Example 1: Adaptive Reflection Strategy")
print("-" * 40)

# Initialize reflection components
reflection_strategy = ReflectionStrategy()
quality_assessor = QualityAssessment()

# Create self-reflecting agent
class SelfReflectingAgent(Agent):
    def __init__(self, reflection_strategy: ReflectionStrategy, quality_assessor: QualityAssessment, **kwargs):
        super().__init__(**kwargs)
        self.reflection_strategy = reflection_strategy
        self.quality_assessor = quality_assessor
        self.reflection_history = []
    
    def reflect_and_improve(self, initial_response: str, task_context: Dict[str, Any]) -> str:
        """Perform self-reflection and iterative improvement"""
        
        # Select appropriate strategy
        task_type = task_context.get("task_type", "general")
        strategy_name = self.reflection_strategy.select_strategy(task_type, task_context)
        strategy_config = self.reflection_strategy.get_strategy_config(strategy_name)
        
        print(f"🧠 Selected reflection strategy: {strategy_name}")
        print(f"Max iterations: {strategy_config['max_iterations']}")
        print(f"Quality threshold: {strategy_config['quality_threshold']}")
        
        current_response = initial_response
        iteration = 0
        
        while iteration < strategy_config["max_iterations"]:
            iteration += 1
            print(f"\n--- Reflection Iteration {iteration} ---")
            
            # Assess current quality
            quality_assessment = self.quality_assessor.assess_quality(current_response, task_context)
            print(f"Quality Score: {quality_assessment['overall_score']:.2f}")
            
            # Check if we should continue reflecting
            if not self.quality_assessor.should_continue_reflection(quality_assessment, strategy_config):
                print("✅ Quality threshold met or minimal improvement detected")
                break
            
            # Generate reflection and improvement
            reflection_prompt = f"""
            Please reflect on this response and suggest specific improvements focusing on: {', '.join(strategy_config['focus_areas'])}
            
            Current response: {current_response}
            
            Current quality scores:
            - Overall: {quality_assessment['overall_score']:.2f}
            - Accuracy: {quality_assessment['criterion_scores']['accuracy']:.2f}
            - Completeness: {quality_assessment['criterion_scores']['completeness']:.2f}
            - Clarity: {quality_assessment['criterion_scores']['clarity']:.2f}
            - Relevance: {quality_assessment['criterion_scores']['relevance']:.2f}
            
            Provide specific suggestions for improvement and then write an improved version.
            """
            
            improved_response = self.start(reflection_prompt)
            
            # Extract improved version (simplified - in practice, use more sophisticated parsing)
            if "improved version:" in improved_response.lower():
                improved_part = improved_response.split("improved version:")[-1].strip()
                if len(improved_part) > len(current_response) * 0.5:  # Reasonable improvement
                    current_response = improved_part
            
            # Log reflection
            self.reflection_history.append({
                "iteration": iteration,
                "quality_before": quality_assessment,
                "reflection_feedback": improved_response[:200] + "...",
                "timestamp": datetime.now().isoformat()
            })
        
        print(f"\n🎯 Reflection completed after {iteration} iterations")
        return current_response

# Test adaptive reflection
research_agent = SelfReflectingAgent(
    reflection_strategy=reflection_strategy,
    quality_assessor=quality_assessor,
    name="Research Agent",
    role="AI Researcher", 
    goal="Conduct thorough and accurate research",
    backstory="Expert researcher with strong analytical and reflection capabilities",
    tools=[internet_search],
    self_reflect=True,
    max_iter=1  # We handle reflection manually
)

task_context = {
    "task_type": "research",
    "urgency": "normal",
    "quality_requirement": "high",
    "expected_word_count": 300,
    "required_elements": ["data", "analysis", "conclusion"],
    "task_keywords": ["artificial intelligence", "market trends", "2024"]
}

initial_research = "AI market is growing. Many companies are investing in AI technologies."
improved_research = research_agent.reflect_and_improve(initial_research, task_context)

print(f"\nFinal improved response: {improved_research[:200]}...")

# Example 2: Multi-Agent Reflection Coordination
print("\n\nExample 2: Multi-Agent Reflection Coordination")
print("-" * 40)

reflection_coordinator = ReflectionCoordinator()

# Simulate multiple agents providing reflections
agent_reflections = [
    {
        "agent": "Technical Analyst",
        "reflection": {
            "quality_score": 0.75,
            "suggestions": ["Add more technical details", "Include performance metrics", "Explain implementation challenges"],
            "strengths": ["Good overview", "Clear structure"],
            "weaknesses": ["Lacks technical depth", "Missing quantitative data"]
        }
    },
    {
        "agent": "Market Expert", 
        "reflection": {
            "quality_score": 0.8,
            "suggestions": ["Include market size data", "Add more technical details", "Discuss competitive landscape"],
            "strengths": ["Good market understanding", "Clear conclusions"],
            "weaknesses": ["Needs more market data", "Could expand on trends"]
        }
    },
    {
        "agent": "Strategy Consultant",
        "reflection": {
            "quality_score": 0.7,
            "suggestions": ["Add strategic implications", "Include implementation challenges", "Discuss risks and opportunities"],
            "strengths": ["Strategic perspective", "Good analysis"],
            "weaknesses": ["Could be more actionable", "Needs risk assessment"]
        }
    }
]

# Add reflections to coordinator
for reflection_data in agent_reflections:
    reflection_coordinator.add_agent_reflection(
        reflection_data["agent"],
        reflection_data["reflection"]
    )

# Coordinate reflections
coordination_result = reflection_coordinator.coordinate_reflections("research_task_001")

print(f"Coordination Results:")
print(f"Participating Agents: {len(coordination_result['participating_agents'])}")
print(f"Consensus Achieved: {coordination_result['consensus_achieved']}")
print(f"Average Quality Score: {coordination_result['average_quality']:.2f}")

if coordination_result["final_recommendations"]:
    print("\nConsensus Recommendations:")
    for rec in coordination_result["final_recommendations"]:
        print(f"  - {rec['suggestion']} (Agreement: {rec['agreement_rate']:.1%})")

# Example 3: Performance Optimization Metrics
print("\n\nExample 3: Reflection Performance Metrics")
print("-" * 40)

# Analyze reflection performance
reflection_performance = {
    "total_reflections": len(research_agent.reflection_history),
    "strategy_adaptations": len(reflection_strategy.adaptation_history),
    "quality_improvements": [],
    "efficiency_metrics": {}
}

# Calculate quality improvements
if len(quality_assessor.quality_history) >= 2:
    initial_quality = quality_assessor.quality_history[0]["overall_score"]
    final_quality = quality_assessor.quality_history[-1]["overall_score"]
    quality_improvement = final_quality - initial_quality
    reflection_performance["quality_improvements"] = {
        "initial_score": initial_quality,
        "final_score": final_quality,
        "improvement": quality_improvement,
        "improvement_percentage": (quality_improvement / initial_quality * 100) if initial_quality > 0 else 0
    }

# Efficiency metrics
reflection_performance["efficiency_metrics"] = {
    "avg_reflection_time": "~2.5s",  # Simulated
    "iterations_to_threshold": len(research_agent.reflection_history),
    "strategy_effectiveness": reflection_strategy.current_strategy
}

print("Reflection Performance Analysis:")
print(f"Total Reflections: {reflection_performance['total_reflections']}")
print(f"Strategy Adaptations: {reflection_performance['strategy_adaptations']}")

if reflection_performance["quality_improvements"]:
    qi = reflection_performance["quality_improvements"]
    print(f"Quality Improvement: {qi['improvement']:.3f} (+{qi['improvement_percentage']:.1f}%)")
    print(f"Final Quality Score: {qi['final_score']:.3f}")

print(f"Iterations to Threshold: {reflection_performance['efficiency_metrics']['iterations_to_threshold']}")
print(f"Current Strategy: {reflection_performance['efficiency_metrics']['strategy_effectiveness']}")

print(f"\n=== Self-Reflection Optimization Summary ===")
print(f"✅ Adaptive reflection strategies implemented")
print(f"✅ Quality-based termination criteria active")
print(f"✅ Multi-agent reflection coordination enabled")
print(f"✅ Performance optimization metrics tracked")
print(f"✅ Context-aware reflection focus areas")
print(f"📊 System effectiveness: Quality improved by {reflection_performance['quality_improvements'].get('improvement_percentage', 0):.1f}%")

print("\nSelf-reflection optimization patterns example complete!")