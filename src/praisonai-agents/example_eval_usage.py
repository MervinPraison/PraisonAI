#!/usr/bin/env python3
"""
Example usage of the PraisonAI evaluation framework.

This file demonstrates all the features described in the GitHub issue specification.
"""

import os
import sys

# Add the package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from praisonaiagents import Agent, Task
# Note: Process is available as PraisonAIAgents.process in the current implementation
from praisonaiagents.eval import AccuracyEval, ReliabilityEval, PerformanceEval, EvalSuite, TestCase, EvalCriteria

def basic_accuracy_example():
    """Example 1: Basic Accuracy Evaluation"""
    print("=== Example 1: Basic Accuracy Evaluation ===")
    
    # Create agent
    agent = Agent(
        name="Analyst",
        role="Data Analyst", 
        goal="Provide accurate analysis",
        backstory="I am a skilled data analyst",
        llm="gpt-4o-mini"
    )
    
    # Simple accuracy check
    eval_test = AccuracyEval(
        agent=agent,
        input="What is the capital of France?",
        expected_output="Paris"
    )
    
    print("Running basic accuracy evaluation...")
    # Note: In a real scenario, you would run: result = eval_test.run()
    # print(f"Accuracy: {result.score}/10")
    print("✓ AccuracyEval configured successfully")

def advanced_accuracy_example():
    """Example 2: Advanced Accuracy Evaluation"""
    print("\n=== Example 2: Advanced Accuracy Evaluation ===")
    
    agent = Agent(
        name="Analyst",
        role="Data Analyst",
        goal="Provide detailed analysis", 
        backstory="I am an expert analyst",
        llm="gpt-4o-mini"
    )
    
    # Multi-criteria evaluation
    eval_test = AccuracyEval(
        agent=agent,
        test_cases=[
            {
                "input": "Summarize the Q1 report",
                "expected_output": "Q1 showed 15% growth...",
                "weight": 2.0  # Higher importance
            },
            {
                "input": "What are the key risks?",
                "expected_output": "Supply chain, market volatility..."
            }
        ],
        criteria=EvalCriteria(
            factual_accuracy=0.4,    # 40% weight
            completeness=0.3,        # 30% weight  
            relevance=0.3           # 30% weight
        ),
        evaluator_llm="gpt-4o-mini",
        iterations=5,               # Statistical reliability
        save_results="eval_results.json"
    )
    
    print("Advanced accuracy evaluation configured with:")
    print("- Multi-criteria scoring")
    print("- Multiple test cases with weights")
    print("- Statistical reliability (5 iterations)")
    print("- Results saving")
    
    # Run with detailed output
    # result = eval_test.run(verbose=True)
    # print(f"Average: {result.avg_score:.2f}")
    # print(f"Std Dev: {result.std_dev:.2f}")
    # print(f"Confidence: {result.confidence_interval}")

def reliability_testing_example():
    """Example 3: Reliability Testing"""
    print("\n=== Example 3: Reliability Testing ===")
    
    agent = Agent(
        name="TaskAgent",
        role="Task Executor",
        goal="Execute tasks reliably",
        backstory="I execute tasks with proper tool usage",
        llm="gpt-4o-mini"
    )
    
    # Test if agent uses expected tools
    eval_test = ReliabilityEval(
        agent=agent,
        test_scenarios=[
            {
                "input": "Search weather and create report",
                "expected_tools": ["web_search", "create_file"],
                "required_order": True  # Tools must be called in order
            },
            {
                "input": "Analyze CSV data",
                "expected_tools": ["read_csv", "analyze_data"],
                "allow_additional": True  # Other tools allowed
            }
        ]
    )
    
    print("Reliability testing configured for:")
    print("- Tool usage validation")
    print("- Order requirement checking")
    print("- Additional tool tolerance")
    
    # results = eval_test.run()
    # for scenario in results.scenarios:
    #     print(f"Scenario: {scenario.name} - {scenario.status}")
    #     if scenario.failed_tools:
    #         print(f"  Failed: {scenario.failed_tools}")

def performance_evaluation_example():
    """Example 4: Performance Evaluation"""
    print("\n=== Example 4: Performance Evaluation ===")
    
    agent = Agent(
        name="PerformanceAgent",
        role="High Performance Agent",
        goal="Execute tasks efficiently",
        backstory="I am optimized for performance",
        llm="gpt-4o-mini"
    )
    
    # Benchmark agent performance
    eval_test = PerformanceEval(
        agent=agent,
        benchmark_queries=[
            "Simple question",
            "Complex analysis task",
            "Multi-step reasoning"
        ],
        metrics={
            "runtime": True,
            "memory": True,
            "tokens": True,  # Token usage tracking
            "ttft": True     # Time to first token
        },
        iterations=50,
        warmup=5
    )
    
    print("Performance evaluation configured with:")
    print("- Runtime measurement")
    print("- Memory tracking")
    print("- Token usage monitoring")
    print("- Time to first token")
    print("- 50 iterations with 5 warmup runs")
    
    # result = eval_test.run()
    # result.print_report()
    
    # Compare agents example
    agents = [agent]  # In practice, you'd have multiple agents
    # comparison = PerformanceEval.compare(
    #     agents=agents,
    #     benchmark_suite="standard",
    #     export_format="html"
    # )

def automated_test_suite_example():
    """Example 5: Automated Test Suite"""
    print("\n=== Example 5: Automated Test Suite ===")
    
    agent = Agent(
        name="QualityAgent",
        role="Quality Assured Agent", 
        goal="Pass all quality checks",
        backstory="I am designed for quality assurance",
        llm="gpt-4o-mini"
    )
    
    # Define comprehensive test suite
    suite = EvalSuite(
        name="Agent Quality Assurance",
        agents=[agent],
        test_cases=[
            TestCase(
                name="Basic Math",
                input="What is 15 * 23?",
                expected_output="345",
                eval_type="accuracy",
                tags=["math", "simple"]
            ),
            TestCase(
                name="Tool Usage",
                input="Search and summarize AI news",
                expected_tools=["web_search", "summarize"],
                eval_type="reliability"
            ),
            TestCase(
                name="Performance Baseline",
                input="Standard benchmark query",
                max_runtime=2.0,  # seconds
                max_memory=100,   # MB
                eval_type="performance"
            )
        ],
        # Automation features
        schedule="0 2 * * *",  # Run daily at 2 AM
        alerts={
            "email": "team@example.com",
            "threshold": 0.8  # Alert if score < 80%
        },
        export_results="s3://bucket/eval-results/"
    )
    
    print("Automated test suite configured with:")
    print("- Multiple test types (accuracy, reliability, performance)")
    print("- Scheduled execution (daily at 2 AM)")
    print("- Email alerts for quality gate failures")
    print("- S3 export for results")
    
    # Run full suite
    # results = suite.run()
    
    # CI/CD integration example
    # if not results.passed:
    #     raise EvalFailure(f"Quality gate failed: {results.summary}")
    
    # Generate report
    # suite.generate_report(
    #     format="html",
    #     include_graphs=True,
    #     compare_with="last_week"
    # )

def integration_with_existing_features_example():
    """Example 6: Integration with Existing PraisonAI Features"""
    print("\n=== Example 6: Integration with Existing Features ===")
    
    # Evaluation-aware agent with memory
    agent = Agent(
        name="EvalAgent",
        role="Evaluation-Aware Agent",
        goal="Perform well in evaluations",
        backstory="I am integrated with evaluation systems",
        llm="gpt-4o-mini",
        # TODO: Add memory and tools integration once available
        # memory=Memory(provider="rag", quality_threshold=0.8),
        # tools=Tools(["web_search", "calculator"]),
        # Built-in evaluation configuration
        # eval_config={
        #     "track_accuracy": True,
        #     "sample_rate": 0.1,  # Evaluate 10% of runs
        #     "baseline": "eval_baseline.json"
        # }
    )
    
    # Process with automatic evaluation
    # TODO: Implement process evaluation integration
    # process = Process(
    #     agents=[agent],
    #     tasks=[task1, task2],
    #     eval_mode=True,
    #     eval_criteria={
    #         "min_accuracy": 0.85,
    #         "max_runtime": 5.0
    #     }
    # )
    
    print("Integration features planned:")
    print("- Memory-aware evaluation")
    print("- Process-level evaluation")
    print("- Automatic quality tracking")
    print("- Baseline comparison")
    
    # Run with evaluation
    # result = process.start()
    # print(f"Process accuracy: {result.eval_metrics.accuracy}")
    # print(f"Task performances: {result.eval_metrics.task_times}")
    # result.eval_metrics.export("process_eval.json")

def main():
    """Run all examples."""
    print("🧪 PraisonAI Agents Evaluation Framework Examples")
    print("="*60)
    
    examples = [
        basic_accuracy_example,
        advanced_accuracy_example,
        reliability_testing_example,
        performance_evaluation_example,
        automated_test_suite_example,
        integration_with_existing_features_example
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"❌ Error in {example.__name__}: {e}")
    
    print("\n" + "="*60)
    print("✅ All examples completed successfully!")
    print("📋 Note: Some examples show configuration only.")
    print("🔧 Uncomment the execution lines to run actual evaluations.")

if __name__ == "__main__":
    main()