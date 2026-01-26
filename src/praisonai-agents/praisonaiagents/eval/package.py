"""Evaluation package and case definitions."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class EvalCase:
    """A single evaluation case.
    
    Example:
        case = EvalCase(
            name="math_addition",
            input="What is 2 + 2?",
            expected="4",
            criteria=["answer_correct", "response_concise"]
        )
    """
    name: str
    input: str
    expected: Optional[str] = None
    criteria: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    
    def __post_init__(self):
        if not self.name:
            raise ValueError("EvalCase must have a name")
        if not self.input:
            raise ValueError("EvalCase must have an input")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "input": self.input,
            "expected": self.expected,
            "criteria": self.criteria,
            "metadata": self.metadata,
            "timeout_seconds": self.timeout_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalCase":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            input=data["input"],
            expected=data.get("expected"),
            criteria=data.get("criteria", []),
            metadata=data.get("metadata", {}),
            timeout_seconds=data.get("timeout_seconds", 30.0),
        )


@dataclass
class EvalResult:
    """Result of running a single eval case."""
    case_name: str
    passed: bool
    score: float  # 0.0 to 1.0
    actual_output: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    criteria_scores: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_name": self.case_name,
            "passed": self.passed,
            "score": self.score,
            "actual_output": self.actual_output,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "criteria_scores": self.criteria_scores,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalResult":
        """Create from dictionary."""
        return cls(
            case_name=data["case_name"],
            passed=data["passed"],
            score=data["score"],
            actual_output=data.get("actual_output"),
            error=data.get("error"),
            latency_ms=data.get("latency_ms", 0.0),
            criteria_scores=data.get("criteria_scores", {}),
        )


@dataclass
class EvalReport:
    """Aggregated report from running an eval package."""
    package_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    average_score: float
    results: List[EvalResult] = field(default_factory=list)
    thresholds_met: Dict[str, bool] = field(default_factory=dict)
    
    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed_cases / self.total_cases
    
    @property
    def all_passed(self) -> bool:
        return self.failed_cases == 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "average_score": self.average_score,
            "pass_rate": self.pass_rate,
            "thresholds_met": self.thresholds_met,
            "results": [r.to_dict() for r in self.results],
        }


@dataclass
class EvalPackage:
    """A distributable evaluation package.
    
    Example:
        package = EvalPackage(
            name="math_eval",
            description="Basic math evaluation",
            cases=[case1, case2, case3],
            thresholds={"accuracy": 0.9, "latency_p95_ms": 1000}
        )
    """
    name: str
    description: str = ""
    version: str = "1.0.0"
    cases: List[EvalCase] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=dict)
    seed: Optional[int] = None  # For deterministic runs
    
    def __post_init__(self):
        if not self.name:
            raise ValueError("EvalPackage must have a name")
    
    def add_case(self, case: EvalCase) -> None:
        """Add an eval case to the package."""
        self.cases.append(case)
    
    def add_cases(self, cases: List[EvalCase]) -> None:
        """Add multiple eval cases."""
        self.cases.extend(cases)
    
    def __len__(self) -> int:
        return len(self.cases)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "cases": [c.to_dict() for c in self.cases],
            "thresholds": self.thresholds,
            "seed": self.seed,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalPackage":
        """Create from dictionary."""
        cases = [EvalCase.from_dict(c) for c in data.get("cases", [])]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            cases=cases,
            thresholds=data.get("thresholds", {}),
            seed=data.get("seed"),
        )


class EvalRunnerProtocol(Protocol):
    """Protocol for eval package runners."""
    
    def run(
        self,
        package: EvalPackage,
        agent: Any,
        **kwargs
    ) -> EvalReport:
        """Run an eval package against an agent."""
        ...
    
    async def run_async(
        self,
        package: EvalPackage,
        agent: Any,
        **kwargs
    ) -> EvalReport:
        """Async version of run."""
        ...
