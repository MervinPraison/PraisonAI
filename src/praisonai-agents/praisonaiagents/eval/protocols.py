"""
Protocols for PraisonAI Agents Evaluation Framework.

Provides Protocol interfaces for grading and evaluation to enable:
- DRY: Common grading logic shared across eval and train modules
- Mocking: Easy testing without real LLM calls
- Extensibility: Custom grader implementations

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, Optional, List, Dict, Any


@runtime_checkable
class GradeResultProtocol(Protocol):
    """
    Protocol for grading results.
    
    Defines the minimal interface for any grading result.
    """
    score: float
    reasoning: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        ...


@runtime_checkable
class GraderProtocol(Protocol):
    """
    Protocol for LLM-as-judge grading.
    
    Defines the interface for grading agent outputs using an LLM.
    Implementations include AccuracyEvaluator, CriteriaEvaluator, and TrainingGrader.
    
    Example:
        ```python
        class MockGrader:
            model = "mock"
            temperature = 0.1
            
            def grade(self, input_text, output, expected_output=None):
                return MockGradeResult(score=8.0, reasoning="Mock")
        
        # Use in tests
        grader: GraderProtocol = MockGrader()
        result = grader.grade("test", "output")
        ```
    """
    model: str
    temperature: float
    
    def grade(
        self,
        input_text: str,
        output: str,
        expected_output: Optional[str] = None,
    ) -> GradeResultProtocol:
        """
        Grade an agent output.
        
        Args:
            input_text: The input given to the agent
            output: The agent's output to grade
            expected_output: Optional expected output for comparison
            
        Returns:
            A GradeResultProtocol with score and reasoning
        """
        ...


@runtime_checkable
class ScoredResultProtocol(Protocol):
    """
    Protocol for scored evaluation results.
    
    Defines the interface for results that have scores and statistics.
    """
    @property
    def scores(self) -> List[float]:
        """Get list of all scores."""
        ...
    
    @property
    def avg_score(self) -> float:
        """Calculate average score."""
        ...
    
    @property
    def passed(self) -> bool:
        """Check if evaluation passed."""
        ...
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        ...
    
    def print_summary(self) -> None:
        """Print a summary of the results."""
        ...


@runtime_checkable
class AsyncGraderProtocol(Protocol):
    """
    Async Protocol for LLM-as-judge grading.
    """
    model: str
    temperature: float
    
    async def grade_async(
        self,
        input_text: str,
        output: str,
        expected_output: Optional[str] = None,
    ) -> GradeResultProtocol:
        """Grade an agent output asynchronously."""
        ...


__all__ = [
    'GradeResultProtocol',
    'GraderProtocol',
    'ScoredResultProtocol',
    'AsyncGraderProtocol',
]
