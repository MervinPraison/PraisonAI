"""
Agent Training Module.

Iteratively improve agent behavior through feedback loops.

Two Modes:
1. **LLM-as-Judge (default)**: Automated review and optimization
   - Agent runs with input
   - LLM grades the output (1-10 score)
   - LLM suggests improvements
   - Agent re-runs with improvements
   - Repeat for N iterations

2. **Human-in-the-Loop (--human flag)**: Interactive feedback
   - Agent runs with input
   - Human reviews and provides feedback
   - Agent re-runs with human feedback
   - Repeat for N iterations

Usage:
    # CLI
    praisonai train agents my_agent.yaml
    praisonai train agents my_agent.yaml --human
    praisonai train agents my_agent.yaml --iterations 5
    
    # Python
    from praisonai.train.agents import AgentTrainer, TrainingScenario
    
    trainer = AgentTrainer(agent=my_agent)
    report = trainer.run()
"""

__all__ = [
    "AgentTrainer",
    "TrainingScenario",
    "TrainingIteration",
    "TrainingReport",
    "TrainingGrader",
    "TrainingStorage",
]


def __getattr__(name: str):
    """Lazy load components."""
    if name == "AgentTrainer":
        from .orchestrator import AgentTrainer
        return AgentTrainer
    
    if name == "TrainingScenario":
        from .models import TrainingScenario
        return TrainingScenario
    
    if name == "TrainingIteration":
        from .models import TrainingIteration
        return TrainingIteration
    
    if name == "TrainingReport":
        from .models import TrainingReport
        return TrainingReport
    
    if name == "TrainingGrader":
        from .grader import TrainingGrader
        return TrainingGrader
    
    if name == "TrainingStorage":
        from .storage import TrainingStorage
        return TrainingStorage
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
