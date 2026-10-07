"""
Evaluation CLI feature for PraisonAI.

Provides CLI commands for running agent evaluations.
"""

import os
import json
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@contextmanager
def _agents_from_yaml(agent_file: str):
    """Yield the agent(s) defined in ``agent_file`` without running them.

    Mirrors the one working construction pattern (``_entrypoint.run``): resolve
    a framework adapter via the registry, build the LLM config list, then
    construct ``AgentsGenerator`` with its required args.

    This is a **context manager** on purpose: a YAML agent with a
    ``tool_timeout`` has its sync tools wrapped around the generator's own
    thread-pool executor, which ``close()`` tears down. The evaluator drives
    the agent *after* loading, so the generator must stay open for the whole
    evaluation — otherwise the first wrapped tool call hits a closed executor.
    Callers therefore evaluate *inside* the ``with`` block. The framework is
    resolved from the YAML (``framework:`` key) when present so a file written
    for another supported adapter is not silently rebuilt with the default.
    """
    from praisonai.framework_adapters.registry import get_default_registry
    from praisonai.llm.config import build_config_list
    from praisonai.agents_generator import AgentsGenerator

    registry = get_default_registry()
    framework = _framework_from_yaml(agent_file) or registry.pick_default()
    adapter = registry.create(registry.resolve_or_default(framework))
    config_list = build_config_list()

    with AgentsGenerator(
        agent_file=agent_file,
        framework=adapter.name,
        config_list=config_list,
        adapter=adapter,
    ) as gen:
        yield gen.build_agents()


def _framework_from_yaml(agent_file: str) -> Optional[str]:
    """Return the ``framework`` declared in ``agent_file`` (``None`` if absent).

    A YAML file may target a specific adapter (e.g. ``framework: crewai``); the
    loader must honour that rather than always rebuilding with the registry
    default. Best-effort: any read/parse error falls back to ``None`` so the
    caller uses the default framework.
    """
    try:
        import yaml
        with open(agent_file, "r") as fh:
            data = yaml.safe_load(fh) or {}
        fw = data.get("framework") if isinstance(data, dict) else None
        return fw if isinstance(fw, str) and fw.strip() else None
    except Exception:  # noqa: BLE001 — best-effort; fall back to default
        return None


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
                # Load from agents.yaml and evaluate inside the generator's
                # lifetime so tool_timeout-wrapped tools keep a live executor.
                try:
                    with _agents_from_yaml(agent_file) as agents:
                        if not agents:
                            return {"error": "No agents found in configuration"}
                        agent = agents[0] if isinstance(agents, list) else agents
                        evaluator = AccuracyEvaluator(
                            agent=agent,
                            input_text=input_text,
                            expected_output=expected_output,
                            num_iterations=iterations,
                            model=model,
                            save_results_path=output_file,
                            verbose=self.verbose
                        )
                        return evaluator.run(print_summary=True).to_dict()
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
        except ImportError as e:
            logger.error(f"Failed to import evaluation modules: {e}")
            return {"error": str(e)}
        
        try:
            with _agents_from_yaml(agent_file) as agents:
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

                return evaluator.run(print_summary=True).to_dict()

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
        except ImportError as e:
            logger.error(f"Failed to import evaluation modules: {e}")
            return {"error": str(e)}
        
        try:
            with _agents_from_yaml(agent_file) as agents:
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

                return evaluator.run(print_summary=True).to_dict()

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
        except ImportError as e:
            logger.error(f"Failed to import evaluation modules: {e}")
            return {"error": str(e)}
        
        try:
            with _agents_from_yaml(agent_file) as agents:
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

                return evaluator.run(print_summary=True).to_dict()

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
