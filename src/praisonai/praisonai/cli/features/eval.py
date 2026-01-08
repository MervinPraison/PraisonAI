"""
Evaluation CLI feature for PraisonAI.

Provides CLI commands for running agent evaluations.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class EvalHandler:
    """Handler for evaluation CLI commands."""
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the evaluation handler.
        
        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
    
    def run_accuracy(
        self,
        agent_file: Optional[str] = None,
        input_text: str = "",
        expected_output: str = "",
        iterations: int = 1,
        model: Optional[str] = None,
        output_file: Optional[str] = None,
        prompt: Optional[str] = None,
        llm: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run accuracy evaluation on an agent.
        
        Args:
            agent_file: Path to agents.yaml file (optional if prompt is provided)
            input_text: Input to provide to the agent
            expected_output: Expected output to compare against
            iterations: Number of evaluation iterations
            model: LLM model for judging
            output_file: Path to save results
            prompt: Direct prompt (alternative to agent_file)
            llm: LLM model for the agent (when using prompt)
            
        Returns:
            Evaluation result dictionary
        """
        try:
            from praisonaiagents.eval import AccuracyEvaluator
            from praisonaiagents import Agent
        except ImportError as e:
            logger.error(f"Failed to import evaluation modules: {e}")
            return {"error": str(e)}
        
        try:
            # Create agent either from file or from prompt
            if prompt:
                # Direct prompt mode - create agent on the fly
                agent = Agent(
                    name="EvalAgent",
                    role="Assistant",
                    goal="Complete the given task",
                    backstory="You are a helpful assistant.",
                    llm=llm or model or "gpt-4o-mini", output="minimal"
                )
                # Use prompt as input if input_text not provided
                if not input_text:
                    input_text = prompt
            elif agent_file:
                # Load from agents.yaml
                try:
                    from praisonai.agents_generator import AgentsGenerator
                    generator = AgentsGenerator(agent_file)
                    agents = generator.generate_agents()
                    
                    if not agents:
                        return {"error": "No agents found in configuration"}
                    
                    agent = agents[0] if isinstance(agents, list) else agents
                except Exception as e:
                    return {"error": f"Failed to load agents from {agent_file}: {e}"}
            else:
                return {"error": "Either --agent or --prompt must be provided"}
            
            evaluator = AccuracyEvaluator(
                agent=agent,
                input_text=input_text,
                expected_output=expected_output,
                num_iterations=iterations,
                model=model,
                save_results_path=output_file,
                verbose=self.verbose
            )
            
            result = evaluator.run(print_summary=True)
            return result.to_dict()
            
        except Exception as e:
            logger.error(f"Accuracy evaluation failed: {e}")
            return {"error": str(e)}
    
    def run_performance(
        self,
        agent_file: str,
        input_text: str = "Hello",
        iterations: int = 10,
        warmup: int = 2,
        track_memory: bool = True,
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run performance evaluation on an agent.
        
        Args:
            agent_file: Path to agents.yaml file
            input_text: Input to provide to the agent
            iterations: Number of benchmark iterations
            warmup: Number of warmup runs
            track_memory: Whether to track memory usage
            output_file: Path to save results
            
        Returns:
            Evaluation result dictionary
        """
        try:
            from praisonaiagents.eval import PerformanceEvaluator
            from praisonai.agents_generator import AgentsGenerator
        except ImportError as e:
            logger.error(f"Failed to import evaluation modules: {e}")
            return {"error": str(e)}
        
        try:
            generator = AgentsGenerator(agent_file)
            agents = generator.generate_agents()
            
            if not agents:
                return {"error": "No agents found in configuration"}
            
            agent = agents[0] if isinstance(agents, list) else agents
            
            evaluator = PerformanceEvaluator(
                agent=agent,
                input_text=input_text,
                num_iterations=iterations,
                warmup_runs=warmup,
                track_memory=track_memory,
                save_results_path=output_file,
                verbose=self.verbose
            )
            
            result = evaluator.run(print_summary=True)
            return result.to_dict()
            
        except Exception as e:
            logger.error(f"Performance evaluation failed: {e}")
            return {"error": str(e)}
    
    def run_reliability(
        self,
        agent_file: str,
        input_text: str,
        expected_tools: List[str],
        forbidden_tools: Optional[List[str]] = None,
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run reliability evaluation on an agent.
        
        Args:
            agent_file: Path to agents.yaml file
            input_text: Input to provide to the agent
            expected_tools: List of tools that should be called
            forbidden_tools: List of tools that should NOT be called
            output_file: Path to save results
            
        Returns:
            Evaluation result dictionary
        """
        try:
            from praisonaiagents.eval import ReliabilityEvaluator
            from praisonai.agents_generator import AgentsGenerator
        except ImportError as e:
            logger.error(f"Failed to import evaluation modules: {e}")
            return {"error": str(e)}
        
        try:
            generator = AgentsGenerator(agent_file)
            agents = generator.generate_agents()
            
            if not agents:
                return {"error": "No agents found in configuration"}
            
            agent = agents[0] if isinstance(agents, list) else agents
            
            evaluator = ReliabilityEvaluator(
                agent=agent,
                input_text=input_text,
                expected_tools=expected_tools,
                forbidden_tools=forbidden_tools,
                save_results_path=output_file,
                verbose=self.verbose
            )
            
            result = evaluator.run(print_summary=True)
            return result.to_dict()
            
        except Exception as e:
            logger.error(f"Reliability evaluation failed: {e}")
            return {"error": str(e)}
    
    def run_criteria(
        self,
        agent_file: str,
        input_text: str,
        criteria: str,
        scoring_type: str = "numeric",
        threshold: float = 7.0,
        iterations: int = 1,
        model: Optional[str] = None,
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run criteria-based evaluation on an agent.
        
        Args:
            agent_file: Path to agents.yaml file
            input_text: Input to provide to the agent
            criteria: Criteria to evaluate against
            scoring_type: "numeric" or "binary"
            threshold: Score threshold for passing (numeric mode)
            iterations: Number of evaluation iterations
            model: LLM model for judging
            output_file: Path to save results
            
        Returns:
            Evaluation result dictionary
        """
        try:
            from praisonaiagents.eval import CriteriaEvaluator
            from praisonai.agents_generator import AgentsGenerator
        except ImportError as e:
            logger.error(f"Failed to import evaluation modules: {e}")
            return {"error": str(e)}
        
        try:
            generator = AgentsGenerator(agent_file)
            agents = generator.generate_agents()
            
            if not agents:
                return {"error": "No agents found in configuration"}
            
            agent = agents[0] if isinstance(agents, list) else agents
            
            evaluator = CriteriaEvaluator(
                criteria=criteria,
                agent=agent,
                input_text=input_text,
                scoring_type=scoring_type,
                threshold=threshold,
                num_iterations=iterations,
                model=model,
                save_results_path=output_file,
                verbose=self.verbose
            )
            
            result = evaluator.run(print_summary=True)
            return result.to_dict()
            
        except Exception as e:
            logger.error(f"Criteria evaluation failed: {e}")
            return {"error": str(e)}
    
    def run_batch(
        self,
        agent_file: str,
        test_file: str,
        eval_type: str = "accuracy",
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run batch evaluation from a test file.
        
        Args:
            agent_file: Path to agents.yaml file
            test_file: Path to JSON test file with test cases
            eval_type: Type of evaluation ("accuracy", "criteria")
            output_file: Path to save results
            
        Returns:
            Batch evaluation results
        """
        try:
            with open(test_file, 'r') as f:
                test_cases = json.load(f)
        except Exception as e:
            return {"error": f"Failed to load test file: {e}"}
        
        results = []
        for i, test_case in enumerate(test_cases):
            if self.verbose:
                print(f"Running test case {i + 1}/{len(test_cases)}")
            
            if eval_type == "accuracy":
                result = self.run_accuracy(
                    agent_file=agent_file,
                    input_text=test_case.get("input", ""),
                    expected_output=test_case.get("expected", ""),
                    iterations=test_case.get("iterations", 1)
                )
            elif eval_type == "criteria":
                result = self.run_criteria(
                    agent_file=agent_file,
                    input_text=test_case.get("input", ""),
                    criteria=test_case.get("criteria", ""),
                    scoring_type=test_case.get("scoring_type", "numeric"),
                    threshold=test_case.get("threshold", 7.0)
                )
            else:
                result = {"error": f"Unknown eval type: {eval_type}"}
            
            results.append({
                "test_case": i + 1,
                "input": test_case.get("input", ""),
                "result": result
            })
        
        batch_result = {
            "total_tests": len(test_cases),
            "eval_type": eval_type,
            "results": results
        }
        
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    json.dump(batch_result, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to save batch results: {e}")
        
        return batch_result


def handle_eval_command(args) -> int:
    """
    Handle the eval CLI command.
    
    Args:
        args: Command line arguments (list or parsed namespace)
        
    Returns:
        Exit code
    """
    import argparse
    
    # If args is a list, parse it first
    if isinstance(args, list):
        parser = argparse.ArgumentParser(prog="praisonai eval")
        subparsers = parser.add_subparsers(dest='eval_type')
        add_eval_parser_subcommands(subparsers)
        
        try:
            args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        if not args.eval_type:
            parser.print_help()
            print("\n[bold]Examples:[/bold]")
            print("  praisonai eval accuracy --prompt \"What is 2+2?\" --expected \"4\"")
            print("  praisonai eval performance --agent agents.yaml --input \"Hello\"")
            return 0
    
    handler = EvalHandler(verbose=getattr(args, 'verbose', False))
    
    eval_type = getattr(args, 'eval_type', 'accuracy')
    agent_file = getattr(args, 'agent', None)
    output_file = getattr(args, 'output', None)
    prompt = getattr(args, 'prompt', None)
    llm = getattr(args, 'llm', None)
    
    # If no agent file and no prompt, check if agents.yaml exists
    if not agent_file and not prompt:
        import os
        if os.path.exists('agents.yaml'):
            agent_file = 'agents.yaml'
    
    if eval_type == 'accuracy':
        result = handler.run_accuracy(
            agent_file=agent_file,
            input_text=getattr(args, 'input', ''),
            expected_output=getattr(args, 'expected', ''),
            iterations=getattr(args, 'iterations', 1),
            model=getattr(args, 'model', None),
            output_file=output_file,
            prompt=prompt,
            llm=llm
        )
    elif eval_type == 'performance':
        result = handler.run_performance(
            agent_file=agent_file,
            input_text=getattr(args, 'input', 'Hello'),
            iterations=getattr(args, 'iterations', 10),
            warmup=getattr(args, 'warmup', 2),
            track_memory=getattr(args, 'memory', True),
            output_file=output_file
        )
    elif eval_type == 'reliability':
        expected_tools = getattr(args, 'expected_tools', '').split(',')
        forbidden_tools = getattr(args, 'forbidden_tools', '')
        forbidden_tools = forbidden_tools.split(',') if forbidden_tools else None
        
        result = handler.run_reliability(
            agent_file=agent_file,
            input_text=getattr(args, 'input', ''),
            expected_tools=expected_tools,
            forbidden_tools=forbidden_tools,
            output_file=output_file
        )
    elif eval_type == 'criteria':
        result = handler.run_criteria(
            agent_file=agent_file,
            input_text=getattr(args, 'input', ''),
            criteria=getattr(args, 'criteria', ''),
            scoring_type=getattr(args, 'scoring', 'numeric'),
            threshold=getattr(args, 'threshold', 7.0),
            iterations=getattr(args, 'iterations', 1),
            model=getattr(args, 'model', None),
            output_file=output_file
        )
    elif eval_type == 'batch':
        result = handler.run_batch(
            agent_file=agent_file,
            test_file=getattr(args, 'test_file', ''),
            eval_type=getattr(args, 'batch_type', 'accuracy'),
            output_file=output_file
        )
    else:
        print(f"Unknown evaluation type: {eval_type}")
        return 1
    
    if 'error' in result:
        print(f"Error: {result['error']}")
        return 1
    elif not getattr(args, 'quiet', False):
        print(json.dumps(result, indent=2))
    
    return 0


def add_eval_parser_subcommands(subparsers) -> None:
    """Add eval subcommand parsers to an existing subparsers object."""
    accuracy_parser = subparsers.add_parser('accuracy', help='Run accuracy evaluation')
    accuracy_parser.add_argument('--agent', '-a', help='Agent config file (optional if --prompt used)')
    accuracy_parser.add_argument('--prompt', '-p', type=str, help='Direct prompt (alternative to --agent)')
    accuracy_parser.add_argument('--llm', help='LLM model for agent (when using --prompt)')
    accuracy_parser.add_argument('--input', '-i', help='Input text (defaults to --prompt if not provided)')
    accuracy_parser.add_argument('--expected', '-e', required=True, help='Expected output')
    accuracy_parser.add_argument('--iterations', '-n', type=int, default=1, help='Number of iterations')
    accuracy_parser.add_argument('--model', '-m', help='Judge model')
    accuracy_parser.add_argument('--output', '-o', help='Output file')
    accuracy_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    accuracy_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress JSON output')
    
    perf_parser = subparsers.add_parser('performance', help='Run performance evaluation')
    perf_parser.add_argument('--agent', '-a', default='agents.yaml', help='Agent config file')
    perf_parser.add_argument('--input', '-i', default='Hello', help='Input text')
    perf_parser.add_argument('--iterations', '-n', type=int, default=10, help='Number of iterations')
    perf_parser.add_argument('--warmup', '-w', type=int, default=2, help='Warmup runs')
    perf_parser.add_argument('--memory', action='store_true', default=True, help='Track memory')
    perf_parser.add_argument('--output', '-o', help='Output file')
    perf_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    perf_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress JSON output')


def add_eval_parser(subparsers) -> None:
    """
    Add eval subcommand parser.
    
    Args:
        subparsers: Argument parser subparsers
    """
    eval_parser = subparsers.add_parser(
        'eval',
        help='Run agent evaluations'
    )
    
    eval_subparsers = eval_parser.add_subparsers(dest='eval_type')
    
    accuracy_parser = eval_subparsers.add_parser(
        'accuracy',
        help='Run accuracy evaluation'
    )
    accuracy_parser.add_argument('--agent', '-a', help='Agent config file (optional if --prompt used)')
    accuracy_parser.add_argument('--prompt', '-p', help='Direct prompt (alternative to --agent)')
    accuracy_parser.add_argument('--llm', help='LLM model for agent (when using --prompt)')
    accuracy_parser.add_argument('--input', '-i', help='Input text (defaults to --prompt if not provided)')
    accuracy_parser.add_argument('--expected', '-e', required=True, help='Expected output')
    accuracy_parser.add_argument('--iterations', '-n', type=int, default=1, help='Number of iterations')
    accuracy_parser.add_argument('--model', '-m', help='Judge model')
    accuracy_parser.add_argument('--output', '-o', help='Output file')
    accuracy_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    accuracy_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress JSON output')
    
    perf_parser = eval_subparsers.add_parser(
        'performance',
        help='Run performance evaluation'
    )
    perf_parser.add_argument('--agent', '-a', default='agents.yaml', help='Agent config file')
    perf_parser.add_argument('--input', '-i', default='Hello', help='Input text')
    perf_parser.add_argument('--iterations', '-n', type=int, default=10, help='Number of iterations')
    perf_parser.add_argument('--warmup', '-w', type=int, default=2, help='Warmup runs')
    perf_parser.add_argument('--memory', action='store_true', default=True, help='Track memory')
    perf_parser.add_argument('--output', '-o', help='Output file')
    perf_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    perf_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress JSON output')
    
    rel_parser = eval_subparsers.add_parser(
        'reliability',
        help='Run reliability evaluation'
    )
    rel_parser.add_argument('--agent', '-a', default='agents.yaml', help='Agent config file')
    rel_parser.add_argument('--input', '-i', required=True, help='Input text')
    rel_parser.add_argument('--expected-tools', '-t', required=True, help='Expected tools (comma-separated)')
    rel_parser.add_argument('--forbidden-tools', '-f', help='Forbidden tools (comma-separated)')
    rel_parser.add_argument('--output', '-o', help='Output file')
    rel_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    rel_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress JSON output')
    
    criteria_parser = eval_subparsers.add_parser(
        'criteria',
        help='Run criteria-based evaluation'
    )
    criteria_parser.add_argument('--agent', '-a', default='agents.yaml', help='Agent config file')
    criteria_parser.add_argument('--input', '-i', required=True, help='Input text')
    criteria_parser.add_argument('--criteria', '-c', required=True, help='Evaluation criteria')
    criteria_parser.add_argument('--scoring', '-s', choices=['numeric', 'binary'], default='numeric', help='Scoring type')
    criteria_parser.add_argument('--threshold', type=float, default=7.0, help='Pass threshold')
    criteria_parser.add_argument('--iterations', '-n', type=int, default=1, help='Number of iterations')
    criteria_parser.add_argument('--model', '-m', help='Judge model')
    criteria_parser.add_argument('--output', '-o', help='Output file')
    criteria_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    criteria_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress JSON output')
    
    batch_parser = eval_subparsers.add_parser(
        'batch',
        help='Run batch evaluation from test file'
    )
    batch_parser.add_argument('--agent', '-a', default='agents.yaml', help='Agent config file')
    batch_parser.add_argument('--test-file', '-t', required=True, help='JSON test file')
    batch_parser.add_argument('--batch-type', '-b', choices=['accuracy', 'criteria'], default='accuracy', help='Evaluation type')
    batch_parser.add_argument('--output', '-o', help='Output file')
    batch_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    batch_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress JSON output')
