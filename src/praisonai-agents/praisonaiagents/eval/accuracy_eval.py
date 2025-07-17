"""
Accuracy evaluation for PraisonAI agents.
"""

import json
import time
import logging
from typing import List, Dict, Any, Optional, Union
from ..agent.agent import Agent
from ..main import TaskOutput
from .eval_result import EvalResult, BatchEvalResult
from .eval_criteria import EvalCriteria

logger = logging.getLogger(__name__)

class AccuracyEval:
    """Evaluate agent accuracy against expected outputs."""
    
    def __init__(
        self,
        agent: Agent,
        input: Optional[str] = None,
        expected_output: Optional[str] = None,
        test_cases: Optional[List[Dict[str, Any]]] = None,
        criteria: Optional[EvalCriteria] = None,
        evaluator_llm: Optional[str] = None,
        iterations: int = 1,
        save_results: Optional[str] = None
    ):
        """
        Initialize accuracy evaluation.
        
        Args:
            agent: Agent to evaluate
            input: Single input for basic evaluation
            expected_output: Expected output for basic evaluation
            test_cases: List of test cases with input/expected_output/weight
            criteria: Multi-criteria evaluation weights
            evaluator_llm: LLM model to use for evaluation
            iterations: Number of evaluation iterations for statistical reliability
            save_results: Path to save results JSON file
        """
        self.agent = agent
        self.input = input
        self.expected_output = expected_output
        self.test_cases = test_cases or []
        self.criteria = criteria
        self.evaluator_llm = evaluator_llm or "gpt-4o-mini"
        self.iterations = iterations
        self.save_results = save_results
        
        # Set up basic test case if input/expected_output provided
        if input and expected_output and not test_cases:
            self.test_cases = [{
                'input': input,
                'expected_output': expected_output,
                'weight': 1.0
            }]
    
    def _evaluate_single_output(self, actual_output: str, expected_output: str, criteria: Optional[EvalCriteria] = None) -> float:
        """
        Evaluate a single output against expected result.
        
        Args:
            actual_output: Agent's actual output
            expected_output: Expected output
            criteria: Evaluation criteria (if None, uses simple similarity)
        
        Returns:
            Score from 0-10
        """
        try:
            if criteria is None:
                # Simple string similarity evaluation
                return self._simple_similarity_score(actual_output, expected_output)
            else:
                # Multi-criteria evaluation using LLM
                return self._llm_evaluate_with_criteria(actual_output, expected_output, criteria)
        except Exception as e:
            logger.error(f"Error evaluating output: {e}")
            return 0.0
    
    def _simple_similarity_score(self, actual: str, expected: str) -> float:
        """Simple similarity scoring based on string matching."""
        if not actual or not expected:
            return 0.0
        
        # Normalize strings
        actual_lower = actual.lower().strip()
        expected_lower = expected.lower().strip()
        
        # Exact match
        if actual_lower == expected_lower:
            return 10.0
        
        # Contains expected output
        if expected_lower in actual_lower:
            return 8.0
        
        # Word-level similarity
        actual_words = set(actual_lower.split())
        expected_words = set(expected_lower.split())
        
        if not expected_words:
            return 0.0
        
        intersection = len(actual_words & expected_words)
        union = len(actual_words | expected_words)
        
        if union == 0:
            return 0.0
        
        # Jaccard similarity scaled to 0-7 range
        similarity = (intersection / len(expected_words)) * 7.0
        return min(similarity, 7.0)
    
    def _llm_evaluate_with_criteria(self, actual: str, expected: str, criteria: EvalCriteria) -> float:
        """Use LLM to evaluate output against criteria."""
        try:
            from ..llm import get_openai_client
            
            client = get_openai_client(self.evaluator_llm)
            
            evaluation_prompt = f"""
            Evaluate the following response based on these criteria:
            - Factual Accuracy ({criteria.factual_accuracy*100}%): How factually correct is the response?
            - Completeness ({criteria.completeness*100}%): How complete is the response?
            - Relevance ({criteria.relevance*100}%): How relevant is the response to the expected output?
            
            Expected Output: {expected}
            Actual Output: {actual}
            
            Rate each criterion from 0-10 and provide the scores in this exact JSON format:
            {{
                "factual_accuracy": <score>,
                "completeness": <score>, 
                "relevance": <score>,
                "explanation": "<brief explanation>"
            }}
            """
            
            response = client.chat.completions.create(
                model=self.evaluator_llm,
                messages=[{"role": "user", "content": evaluation_prompt}],
                temperature=0.1
            )
            
            # Parse response
            response_text = response.choices[0].message.content.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]
            
            eval_scores = json.loads(response_text)
            
            # Calculate weighted score
            return criteria.calculate_weighted_score(eval_scores)
            
        except Exception as e:
            logger.error(f"Error in LLM evaluation: {e}")
            # Fallback to simple similarity
            return self._simple_similarity_score(actual, expected)
    
    def run(self, verbose: bool = False) -> Union[EvalResult, BatchEvalResult]:
        """
        Run the accuracy evaluation.
        
        Args:
            verbose: Whether to print detailed output
            
        Returns:
            EvalResult for single iteration, BatchEvalResult for multiple iterations
        """
        try:
            if self.iterations == 1:
                return self._run_single_iteration(verbose)
            else:
                return self._run_multiple_iterations(verbose)
        except Exception as e:
            logger.error(f"Error running evaluation: {e}")
            if self.iterations == 1:
                return EvalResult(score=0.0, success=False, error=str(e))
            else:
                return BatchEvalResult(scores=[], success=False, error=str(e))
    
    def _run_single_iteration(self, verbose: bool = False) -> EvalResult:
        """Run a single evaluation iteration."""
        if not self.test_cases:
            return EvalResult(score=0.0, success=False, error="No test cases provided")
        
        total_score = 0.0
        total_weight = 0.0
        details = {
            'test_case_results': [],
            'evaluation_method': 'llm' if self.criteria else 'similarity'
        }
        
        for i, test_case in enumerate(self.test_cases):
            test_input = test_case.get('input', '')
            expected = test_case.get('expected_output', '')
            weight = test_case.get('weight', 1.0)
            
            if verbose:
                print(f"Running test case {i+1}: {test_input[:50]}...")
            
            # Get agent response
            try:
                task_result = self.agent.execute(test_input)
                if isinstance(task_result, TaskOutput):
                    actual_output = task_result.raw
                else:
                    actual_output = str(task_result)
            except Exception as e:
                logger.error(f"Error executing agent task: {e}")
                actual_output = ""
            
            # Evaluate response
            score = self._evaluate_single_output(actual_output, expected, self.criteria)
            weighted_score = score * weight
            
            total_score += weighted_score
            total_weight += weight
            
            test_result = {
                'input': test_input,
                'expected_output': expected,
                'actual_output': actual_output,
                'score': score,
                'weight': weight,
                'weighted_score': weighted_score
            }
            details['test_case_results'].append(test_result)
            
            if verbose:
                print(f"  Score: {score:.2f}/10 (weight: {weight})")
        
        final_score = total_score / total_weight if total_weight > 0 else 0.0
        
        result = EvalResult(
            score=final_score,
            details=details,
            success=True
        )
        
        if self.save_results:
            self._save_results(result.to_dict())
        
        return result
    
    def _run_multiple_iterations(self, verbose: bool = False) -> BatchEvalResult:
        """Run multiple evaluation iterations."""
        scores = []
        all_details = []
        
        for iteration in range(self.iterations):
            if verbose:
                print(f"\nIteration {iteration + 1}/{self.iterations}")
            
            result = self._run_single_iteration(verbose)
            scores.append(result.score)
            all_details.append(result.details)
        
        batch_result = BatchEvalResult(
            scores=scores,
            details=all_details,
            success=True
        )
        
        if self.save_results:
            self._save_results(batch_result.to_dict())
        
        return batch_result
    
    def _save_results(self, results: Dict[str, Any]):
        """Save evaluation results to file."""
        try:
            with open(self.save_results, 'w') as f:
                json.dump(results, f, indent=2)
            if hasattr(self, 'verbose') and self.verbose:
                print(f"Results saved to {self.save_results}")
        except Exception as e:
            logger.error(f"Error saving results: {e}")