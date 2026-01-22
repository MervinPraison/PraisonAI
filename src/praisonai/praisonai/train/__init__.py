"""
PraisonAI Training Module.

This module provides two types of training:

1. **LLM Fine-tuning** (`praisonai train dataset.json`)
   - Fine-tune language models using Unsloth
   - Requires GPU and heavy dependencies

2. **Agent Training** (`praisonai train agents`)
   - Iteratively improve agent behavior through feedback
   - Two modes:
     - LLM-as-judge (default): Automated review and optimization
     - Human-in-the-loop (--human): Interactive feedback

Usage:
    # LLM Fine-tuning (existing)
    praisonai train dataset.json
    
    # Agent Training (new)
    praisonai train agents my_agent.yaml
    praisonai train agents my_agent.yaml --human
    praisonai train agents my_agent.yaml --iterations 5

Programmatic Usage:
    from praisonai.train.agents import AgentTrainer, TrainingScenario
    
    trainer = AgentTrainer(agent=my_agent)
    report = trainer.run()
"""

__all__ = [
    # Agent training
    "AgentTrainer",
    "TrainingScenario",
    "TrainingIteration",
    "TrainingReport",
    "TrainingGrader",
    "TrainingStorage",
    # LLM fine-tuning (lazy)
    "TrainModel",
]


def __getattr__(name: str):
    """Lazy load training components to avoid heavy imports."""
    # Agent training components (lightweight)
    if name == "AgentTrainer":
        from .agents.orchestrator import AgentTrainer
        return AgentTrainer
    
    if name == "TrainingScenario":
        from .agents.models import TrainingScenario
        return TrainingScenario
    
    if name == "TrainingIteration":
        from .agents.models import TrainingIteration
        return TrainingIteration
    
    if name == "TrainingReport":
        from .agents.models import TrainingReport
        return TrainingReport
    
    if name == "TrainingGrader":
        from .agents.grader import TrainingGrader
        return TrainingGrader
    
    if name == "TrainingStorage":
        from .agents.storage import TrainingStorage
        return TrainingStorage
    
    # LLM fine-tuning (heavy - only load when needed)
    if name == "TrainModel":
        from .llm.trainer import TrainModel
        return TrainModel
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
