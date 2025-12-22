"""
Base evaluator class for PraisonAI Agents evaluation framework.

This module provides the abstract base class that all evaluators inherit from.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union, TYPE_CHECKING
import uuid
import logging

if TYPE_CHECKING:
    from .results import AccuracyResult, PerformanceResult, ReliabilityResult, CriteriaResult

logger = logging.getLogger(__name__)


class BaseEvaluator(ABC):
    """
    Abstract base class for all evaluators in PraisonAI Agents.
    
    Provides common functionality for evaluation lifecycle management,
    result storage, and telemetry integration.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the base evaluator.
        
        Args:
            name: Optional name for this evaluation run
            save_results_path: Optional file path to save results (supports {name}, {eval_id} placeholders)
            verbose: Enable verbose output during evaluation
        """
        self.eval_id = str(uuid.uuid4())[:8]
        self.name = name or f"eval_{self.eval_id}"
        self.save_results_path = save_results_path
        self.verbose = verbose
        self._result = None
    
    def before_run(self) -> None:
        """
        Hook called before evaluation runs.
        Override in subclasses for custom pre-evaluation logic.
        """
        if self.verbose:
            logger.info(f"Starting evaluation: {self.name} (ID: {self.eval_id})")
    
    def after_run(self, result: Any) -> None:
        """
        Hook called after evaluation completes.
        Override in subclasses for custom post-evaluation logic.
        
        Args:
            result: The evaluation result
        """
        if self.verbose:
            logger.info(f"Completed evaluation: {self.name}")
        
        if self.save_results_path:
            self._save_result(result)
    
    async def async_before_run(self) -> None:
        """
        Async hook called before evaluation runs.
        Override in subclasses for custom async pre-evaluation logic.
        """
        self.before_run()
    
    async def async_after_run(self, result: Any) -> None:
        """
        Async hook called after evaluation completes.
        Override in subclasses for custom async post-evaluation logic.
        
        Args:
            result: The evaluation result
        """
        self.after_run(result)
    
    @abstractmethod
    def run(self, **kwargs) -> Any:
        """
        Execute the evaluation synchronously.
        
        Returns:
            Evaluation result (type depends on evaluator)
        """
        pass
    
    async def run_async(self, **kwargs) -> Any:
        """
        Execute the evaluation asynchronously.
        Default implementation calls sync run().
        Override for true async evaluation.
        
        Returns:
            Evaluation result (type depends on evaluator)
        """
        return self.run(**kwargs)
    
    def _save_result(self, result: Any) -> None:
        """
        Save evaluation result to file.
        
        Args:
            result: The evaluation result to save
        """
        if not self.save_results_path:
            return
        
        try:
            import json
            from pathlib import Path
            
            file_path = self.save_results_path.format(
                name=self.name,
                eval_id=self.eval_id
            )
            
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            if hasattr(result, 'to_dict'):
                data = result.to_dict()
            elif hasattr(result, '__dict__'):
                data = result.__dict__
            else:
                data = {"result": str(result)}
            
            path.write_text(json.dumps(data, indent=2, default=str))
            
            if self.verbose:
                logger.info(f"Saved results to: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to save results: {e}")
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, eval_id={self.eval_id!r})"
