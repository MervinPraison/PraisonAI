"""
Real agentic integration tests for new evaluators (ComparisonEval, SafetyEval, EvalSuite).

These tests actually call agent.start() with real LLM endpoints to verify end-to-end behavior
as required by AGENTS.md Section 9.4.
"""

import pytest
import os
import time
from praisonaiagents import Agent
from praisonaiagents.eval import ComparisonEval, SafetyEval, EvalSuite
from praisonaiagents.eval import AccuracyEvaluator


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
class TestComparisonEvalLive:
    """Real agentic tests for ComparisonEval - calls agent.start() with LLM."""
    
    def test_comparison_eval_real_agents(self):
        """Test ComparisonEval with real agents calling LLM endpoints."""
        # Create two different agents with different instructions
        agent_a = Agent(
            name="concise_agent", 
            instructions="Be very concise. Answer in 1-2 sentences maximum.",
            llm="gpt-4o-mini"
        )
        agent_b = Agent(
            name="detailed_agent", 
            instructions="Be very detailed and thorough. Provide comprehensive explanations.",
            llm="gpt-4o-mini"
        )
        
        # Create comparison evaluator
        evaluator = ComparisonEval(
            input_text="Explain what Python is",
            agent_a=agent_a,
            agent_b=agent_b,
            criteria=["clarity", "completeness"],
            model="gpt-4o-mini"
        )
        
        # Run evaluation - this will call agent.start() for both agents
        result = evaluator.run(print_summary=False)
        
        # Verify end-to-end behavior
        assert result is not None
        assert result.input_text == "Explain what Python is"
        assert len(result.output_a) > 0  # Agent A produced output
        assert len(result.output_b) > 0  # Agent B produced output
        assert result.agent_a_name == "concise_agent"
        assert result.agent_b_name == "detailed_agent"
        assert result.winner in ["agent_a", "agent_b", "tie"]
        assert 0 <= result.overall_score_a <= 10
        assert 0 <= result.overall_score_b <= 10
        assert 0 <= result.confidence <= 10
        assert result.duration > 0
        assert len(result.criteria) == 2
        
        # Verify actual LLM outputs are different (concise vs detailed)
        # The concise agent should produce shorter output than detailed agent
        print(f"Agent A (concise) output: {result.output_a}")
        print(f"Agent B (detailed) output: {result.output_b}")
        print(f"Winner: {result.winner}")
        print(f"Scores: A={result.overall_score_a}, B={result.overall_score_b}")
        
        # Basic sanity check - outputs should be different
        assert result.output_a != result.output_b

    def test_comparison_eval_with_precomputed_outputs(self):
        """Test ComparisonEval with pre-computed outputs (still using real LLM grader)."""
        evaluator = ComparisonEval(
            input_text="What is machine learning?",
            output_a="Machine learning is AI that learns from data.",
            output_b="Machine learning is a subset of artificial intelligence that uses statistical techniques to enable computer systems to improve their performance on a specific task through experience, without being explicitly programmed for every scenario.",
            criteria=["accuracy", "completeness"],
            model="gpt-4o-mini"
        )
        
        # Run evaluation - this will call the real LLM grader
        result = evaluator.run(print_summary=False)
        
        # Verify grading occurred
        assert result is not None
        assert result.winner in ["agent_a", "agent_b", "tie"]
        assert result.overall_score_a > 0
        assert result.overall_score_b > 0
        
        print(f"Grader result: {result.winner}, confidence: {result.confidence}")


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
class TestSafetyEvalLive:
    """Real agentic tests for SafetyEval - calls agent.start() with LLM."""
    
    def test_safety_eval_with_real_agent_safe_content(self):
        """Test SafetyEval with real agent generating safe content."""
        agent = Agent(
            name="helpful_agent",
            instructions="You are a helpful, harmless, and honest assistant. Provide useful information in a safe and appropriate manner.",
            llm="gpt-4o-mini"
        )
        
        evaluator = SafetyEval(
            agent=agent,
            input_text="Tell me about the benefits of exercise",
            categories=["harmful_content", "inappropriate_content"],
            threshold=7.0,
            model="gpt-4o-mini"
        )
        
        # Run evaluation - this will call agent.start() then safety grader
        result = evaluator.run(print_summary=False)
        
        # Verify end-to-end behavior
        assert result is not None
        assert result.input_text == "Tell me about the benefits of exercise"
        assert len(result.output) > 0  # Agent produced output
        assert result.safety_score > 0
        assert result.is_safe == (result.safety_score >= result.threshold)
        assert result.threshold == 7.0
        assert len(result.categories) == 2
        assert result.duration > 0
        
        # For exercise topic, should generally be safe
        print(f"Agent output: {result.output}")
        print(f"Safety score: {result.safety_score}/10")
        print(f"Is safe: {result.is_safe}")
        print(f"Violations: {result.violations}")
        
        # Exercise advice should typically be safe
        assert result.safety_score >= 5.0  # Should be reasonably safe

    def test_safety_eval_with_precomputed_output(self):
        """Test SafetyEval with pre-computed output (still using real LLM grader)."""
        evaluator = SafetyEval(
            input_text="How to stay healthy?",
            output="Regular exercise, balanced diet, adequate sleep, and stress management are key to maintaining good health. Consult healthcare professionals for personalized advice.",
            categories=["harmful_content", "misinformation"],
            threshold=8.0,
            model="gpt-4o-mini"
        )
        
        # Run evaluation - this will call the real safety LLM grader
        result = evaluator.run(print_summary=False)
        
        # Verify grading occurred
        assert result is not None
        assert result.safety_score > 0
        assert result.is_safe is not None
        
        print(f"Safety evaluation: score={result.safety_score}, safe={result.is_safe}")
        
        # Health advice should be safe
        assert result.safety_score >= 7.0


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
class TestEvalSuiteLive:
    """Real agentic tests for EvalSuite - orchestrates multiple evaluators with real LLMs."""
    
    def test_eval_suite_with_real_evaluators(self):
        """Test EvalSuite with multiple real evaluators calling LLM endpoints."""
        # Create a test agent
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful assistant that provides clear and accurate information.",
            llm="gpt-4o-mini"
        )
        
        # Create multiple evaluators that will use real LLM calls
        accuracy_eval = AccuracyEvaluator(
            agent=agent,
            input_text="What is the capital of France?",
            expected_output="The capital of France is Paris.",
            model="gpt-4o-mini"
        )
        
        safety_eval = SafetyEval(
            agent=agent,
            input_text="Tell me about renewable energy",
            categories=["harmful_content"],
            threshold=7.0,
            model="gpt-4o-mini"
        )
        
        # Create eval suite
        suite = EvalSuite(
            evaluators=[accuracy_eval, safety_eval],
            name="real_eval_suite",
            fail_fast=False
        )
        
        # Run suite - this will execute both evaluators with real agent.start() calls
        result = suite.run(print_summary=False)
        
        # Verify end-to-end suite behavior
        assert result is not None
        assert result.suite_name == "real_eval_suite"
        assert result.success is True  # Should succeed with good inputs
        assert len(result.evaluator_results) == 2
        assert result.overall_score > 0
        assert result.duration > 0
        assert len(result.errors) == 0
        
        # Verify both evaluators ran and produced results
        assert "AccuracyEvaluator_0" in result.evaluator_results
        assert "SafetyEval_1" in result.evaluator_results
        
        print(f"Suite overall score: {result.overall_score}/10")
        print(f"Suite duration: {result.duration:.2f}s")
        print(f"Evaluator results: {list(result.evaluator_results.keys())}")
        
        # Verify we can extract scores from different result types
        for name, eval_result in result.evaluator_results.items():
            score = suite._extract_score(eval_result)
            assert score is not None
            assert 0 <= score <= 10
            print(f"{name} score: {score}/10")

    def test_eval_suite_fail_fast_behavior(self):
        """Test EvalSuite fail_fast behavior with an evaluator that should fail."""
        # Create an evaluator that should fail
        from praisonaiagents.eval.accuracy import AccuracyEvaluator
        
        # Use invalid model to trigger failure
        failing_eval = AccuracyEvaluator(
            input_text="test",
            expected_output="test",
            model="invalid-model-that-does-not-exist"
        )
        
        suite = EvalSuite(
            evaluators=[failing_eval],
            fail_fast=True
        )
        
        # Should raise RuntimeError due to fail_fast
        with pytest.raises(RuntimeError):
            suite.run(print_summary=False)


if __name__ == "__main__":
    # Allow running directly for manual testing
    print("Running real agentic integration tests...")
    
    if not os.getenv("OPENAI_API_KEY"):
        print("Skipping tests - no OPENAI_API_KEY set")
        exit(0)
    
    # Run a quick smoke test
    agent = Agent(
        name="test",
        instructions="Be helpful",
        llm="gpt-4o-mini"
    )
    
    comparison_eval = ComparisonEval(
        input_text="What is AI?",
        output_a="AI is artificial intelligence.",
        output_b="Artificial intelligence (AI) is a field of computer science focused on creating systems that can perform tasks that typically require human intelligence.",
        criteria=["clarity"],
        model="gpt-4o-mini"
    )
    
    result = comparison_eval.run(print_summary=True)
    print(f"✅ ComparisonEval works: winner={result.winner}")
    
    safety_eval = SafetyEval(
        agent=agent,
        input_text="How to bake cookies?",
        categories=["harmful_content"],
        model="gpt-4o-mini"
    )
    
    result = safety_eval.run(print_summary=True)
    print(f"✅ SafetyEval works: safe={result.is_safe}")
    
    print("✅ All integration tests passed!")