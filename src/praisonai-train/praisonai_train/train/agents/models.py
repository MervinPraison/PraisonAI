"""
Data models for Agent Training.

Provides dataclasses for training scenarios, iterations, and reports.
Designed to be simple and JSON-serializable.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import statistics


@dataclass
class TrainingProfile:
    """
    Consolidated training profile for runtime application.
    
    Contains the actionable suggestions from a training session that can be
    injected into an agent's prompt at runtime via hooks.
    
    Attributes:
        agent_name: Name of the agent this profile is for
        suggestions: List of improvement suggestions
        quality_score: Score from the training iteration
        summary: Summary of the training feedback
        iteration_num: Which iteration this came from
        session_id: The training session ID
        created_at: When this profile was created
    
    Example:
        profile = TrainingProfile(
            agent_name="assistant",
            suggestions=["Be concise", "Use examples"],
            quality_score=8.5,
            summary="Focus on clarity and examples",
            iteration_num=2,
            session_id="train-abc123"
        )
    """
    agent_name: str
    suggestions: List[str]
    quality_score: float
    summary: str
    iteration_num: int
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingProfile":
        """Create from dictionary."""
        return cls(
            agent_name=data["agent_name"],
            suggestions=data.get("suggestions", []),
            quality_score=data.get("quality_score", 0.0),
            summary=data.get("summary", ""),
            iteration_num=data.get("iteration_num", 0),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )
    
    @classmethod
    def from_iteration(
        cls,
        iteration: "TrainingIteration",
        agent_name: str,
        session_id: str,
    ) -> "TrainingProfile":
        """
        Create a TrainingProfile from a TrainingIteration.
        
        Args:
            iteration: The training iteration to use
            agent_name: Name of the agent
            session_id: The training session ID
            
        Returns:
            TrainingProfile with data from the iteration
        """
        return cls(
            agent_name=agent_name,
            suggestions=iteration.suggestions,
            quality_score=iteration.score,
            summary=iteration.feedback,
            iteration_num=iteration.iteration_num,
            session_id=session_id,
        )


@dataclass
class TrainingScenario:
    """
    A scenario for agent training.
    
    Represents a single input/output pair that the agent should learn from.
    
    Attributes:
        id: Unique identifier for this scenario
        input_text: The input prompt to give the agent
        expected_output: Optional expected output for comparison
        context: Additional context or metadata
    
    Example:
        scenario = TrainingScenario(
            id="greeting-1",
            input_text="Hello, how are you?",
            expected_output="I'm doing well, thank you!"
        )
    """
    id: str
    input_text: str
    expected_output: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingScenario":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            input_text=data["input_text"],
            expected_output=data.get("expected_output"),
            context=data.get("context", {})
        )


@dataclass
class TrainingIteration:
    """
    Data from one training iteration.
    
    Captures the input, output, score, and feedback for a single iteration.
    
    Attributes:
        iteration_num: Which iteration this is (1-based)
        scenario_id: ID of the scenario being trained
        input_text: The input given to the agent
        output: The agent's output
        score: Quality score (1-10)
        feedback: Feedback text (from LLM or human)
        suggestions: List of improvement suggestions
        timestamp: When this iteration occurred
        metadata: Additional metadata
    """
    iteration_num: int
    scenario_id: str
    input_text: str
    output: str
    score: float
    feedback: str
    suggestions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingIteration":
        """Create from dictionary."""
        return cls(
            iteration_num=data["iteration_num"],
            scenario_id=data["scenario_id"],
            input_text=data["input_text"],
            output=data["output"],
            score=data["score"],
            feedback=data["feedback"],
            suggestions=data.get("suggestions", []),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            metadata=data.get("metadata", {})
        )


@dataclass
class TrainingReport:
    """
    Summary report of a training session.
    
    Contains all iterations and computed statistics.
    
    Attributes:
        session_id: Unique session identifier
        iterations: List of all training iterations
        total_iterations: Total number of iterations run
        started_at: When training started
        completed_at: When training completed
        metadata: Additional metadata
    """
    session_id: str
    iterations: List[TrainingIteration]
    total_iterations: int
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def scores(self) -> List[float]:
        """Get list of all scores."""
        return [it.score for it in self.iterations]
    
    @property
    def avg_score(self) -> float:
        """Calculate average score across all iterations."""
        if not self.scores:
            return 0.0
        return statistics.mean(self.scores)
    
    @property
    def min_score(self) -> float:
        """Get minimum score."""
        if not self.scores:
            return 0.0
        return min(self.scores)
    
    @property
    def max_score(self) -> float:
        """Get maximum score."""
        if not self.scores:
            return 0.0
        return max(self.scores)
    
    @property
    def improvement(self) -> float:
        """Calculate improvement from first to last iteration."""
        if len(self.scores) < 2:
            return 0.0
        return self.scores[-1] - self.scores[0]
    
    @property
    def passed(self) -> bool:
        """Check if training passed (avg score >= 7)."""
        return self.avg_score >= 7.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "iterations": [it.to_dict() for it in self.iterations],
            "total_iterations": self.total_iterations,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
            "avg_score": self.avg_score,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "improvement": self.improvement,
            "passed": self.passed,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingReport":
        """Create from dictionary."""
        iterations = [
            TrainingIteration.from_dict(it) for it in data.get("iterations", [])
        ]
        return cls(
            session_id=data["session_id"],
            iterations=iterations,
            total_iterations=data["total_iterations"],
            started_at=data.get("started_at", datetime.utcnow().isoformat()),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {})
        )
    
    def get_best_iteration(self) -> Optional[TrainingIteration]:
        """
        Get the iteration with the highest score.
        
        Returns:
            TrainingIteration with highest score, or None if no iterations
        """
        if not self.iterations:
            return None
        return max(self.iterations, key=lambda it: it.score)
    
    def get_iteration(self, iteration_num: int) -> Optional[TrainingIteration]:
        """
        Get a specific iteration by number.
        
        Args:
            iteration_num: The iteration number (1-based)
            
        Returns:
            TrainingIteration or None if not found
        """
        for it in self.iterations:
            if it.iteration_num == iteration_num:
                return it
        return None
    
    def print_summary(self) -> None:
        """Print a summary of the training results."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            table = Table(title="Agent Training Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Session ID", self.session_id)
            table.add_row("Total Iterations", str(self.total_iterations))
            table.add_row("Average Score", f"{self.avg_score:.2f}")
            table.add_row("Min Score", f"{self.min_score:.2f}")
            table.add_row("Max Score", f"{self.max_score:.2f}")
            table.add_row("Improvement", f"{self.improvement:+.2f}")
            table.add_row("Status", "✅ PASSED" if self.passed else "❌ NEEDS WORK")
            
            console.print(table)
        except ImportError:
            print("Agent Training Summary")
            print(f"  Session ID: {self.session_id}")
            print(f"  Total Iterations: {self.total_iterations}")
            print(f"  Average Score: {self.avg_score:.2f}")
            print(f"  Min Score: {self.min_score:.2f}")
            print(f"  Max Score: {self.max_score:.2f}")
            print(f"  Improvement: {self.improvement:+.2f}")
            print(f"  Status: {'PASSED' if self.passed else 'NEEDS WORK'}")
