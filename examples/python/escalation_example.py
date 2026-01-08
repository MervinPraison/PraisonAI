"""
Escalation Pipeline Example.

Demonstrates the progressive escalation from direct response to autonomous mode.
"""

import asyncio
from praisonaiagents.escalation import (
    EscalationPipeline,
    EscalationStage,
    EscalationConfig,
    EscalationTrigger,
    DoomLoopDetector,
    ObservabilityHooks,
    EventType,
)


def demo_signal_detection():
    """Demonstrate signal detection from prompts."""
    print("\n" + "="*60)
    print("SIGNAL DETECTION DEMO")
    print("="*60)
    
    trigger = EscalationTrigger()
    
    # Test various prompts
    test_prompts = [
        ("What is Python?", "Simple question"),
        ("Read the file src/main.py", "File reference"),
        ("Refactor the authentication module and add tests", "Complex task"),
        ("First, analyze the code. Then, fix the bug. Finally, test it.", "Multi-step"),
    ]
    
    for prompt, description in test_prompts:
        signals = trigger.analyze(prompt)
        stage = trigger.recommend_stage(signals)
        
        print(f"\n📝 Prompt: {prompt[:50]}...")
        print(f"   Description: {description}")
        print(f"   Signals: {[s.value for s in signals]}")
        print(f"   Recommended Stage: {stage.name}")


def demo_doom_loop_detection():
    """Demonstrate doom loop detection."""
    print("\n" + "="*60)
    print("DOOM LOOP DETECTION DEMO")
    print("="*60)
    
    detector = DoomLoopDetector()
    detector.start_session()
    
    # Simulate repeated identical actions
    print("\n🔄 Simulating repeated identical actions...")
    for i in range(4):
        detector.record_action(
            action_type="read_file",
            args={"path": "config.py"},
            result="same content",
            success=True,
        )
        
        if detector.is_doom_loop():
            loop_type = detector.get_loop_type()
            recovery = detector.get_recovery_action()
            print(f"   ⚠️  Doom loop detected after {i+1} actions!")
            print(f"   Type: {loop_type.value}")
            print(f"   Recovery: {recovery.value}")
            break
        else:
            print(f"   Action {i+1}: No loop detected")
    
    # Show stats
    stats = detector.get_stats()
    print(f"\n📊 Stats: {stats}")


def demo_observability():
    """Demonstrate observability hooks."""
    print("\n" + "="*60)
    print("OBSERVABILITY DEMO")
    print("="*60)
    
    hooks = ObservabilityHooks()
    
    # Register event handlers
    def on_stage_change(event):
        print(f"   📍 Stage changed: {event.data}")
    
    def on_tool_call(event):
        print(f"   🔧 Tool called: {event.data}")
    
    hooks.on(EventType.STAGE_ESCALATE, on_stage_change)
    hooks.on(EventType.TOOL_CALL_END, on_tool_call)
    
    # Simulate events
    print("\n🎯 Simulating execution events...")
    hooks.start_execution("session_123")
    
    hooks.set_stage(EscalationStage.DIRECT)
    hooks.emit(EventType.STEP_START, {"step": 1})
    hooks.emit(EventType.TOOL_CALL_END, {"tool": "read_file", "path": "main.py"})
    hooks.emit(EventType.STEP_END, {"step": 1})
    
    hooks.emit(EventType.STAGE_ESCALATE, {"from": "DIRECT", "to": "HEURISTIC"})
    hooks.set_stage(EscalationStage.HEURISTIC)
    
    hooks.end_execution(1500.0)
    
    # Show summary
    summary = hooks.get_summary()
    print(f"\n📊 Summary: {summary}")


def demo_stage_descriptions():
    """Show descriptions of each escalation stage."""
    print("\n" + "="*60)
    print("ESCALATION STAGES")
    print("="*60)
    
    trigger = EscalationTrigger()
    
    stages = [
        (EscalationStage.DIRECT, "Simple questions, no tools needed"),
        (EscalationStage.HEURISTIC, "File references, code blocks"),
        (EscalationStage.PLANNED, "Edit intent, test/build tasks"),
        (EscalationStage.AUTONOMOUS, "Multi-step, refactoring tasks"),
    ]
    
    for stage, example in stages:
        desc = trigger.get_stage_description(stage)
        print(f"\n🎯 Stage {stage.value}: {stage.name}")
        print(f"   Description: {desc}")
        print(f"   Example use: {example}")


async def demo_pipeline_analysis():
    """Demonstrate pipeline analysis."""
    print("\n" + "="*60)
    print("PIPELINE ANALYSIS DEMO")
    print("="*60)
    
    config = EscalationConfig(
        max_steps=20,
        max_time_seconds=60,
        auto_escalate=True,
    )
    
    pipeline = EscalationPipeline(config=config)
    
    prompts = [
        "What is a Python decorator?",
        "Read the file src/auth.py and explain it",
        "Refactor the user authentication to use JWT tokens",
    ]
    
    for prompt in prompts:
        stage = pipeline.analyze(prompt)
        print(f"\n📝 Prompt: {prompt[:50]}...")
        print(f"   Recommended Stage: {stage.name}")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("PRAISONAI ESCALATION PIPELINE DEMO")
    print("="*60)
    print("\nThis demo shows the progressive escalation system that")
    print("automatically adjusts execution complexity based on task signals.")
    
    # Run demos
    demo_stage_descriptions()
    demo_signal_detection()
    demo_doom_loop_detection()
    demo_observability()
    asyncio.run(demo_pipeline_analysis())
    
    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print("\nKey takeaways:")
    print("1. Simple tasks stay at DIRECT stage (no tools)")
    print("2. File references trigger HEURISTIC stage")
    print("3. Edit/test tasks trigger PLANNED stage")
    print("4. Multi-step/refactor tasks trigger AUTONOMOUS stage")
    print("5. Doom loop detection prevents infinite loops")
    print("6. Observability hooks enable monitoring")


if __name__ == "__main__":
    main()
