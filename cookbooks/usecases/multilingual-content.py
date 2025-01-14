from praisonaiagents import Agent, Task, PraisonAIAgents
import time
from typing import Dict, List

def generate_base_content():
    """Simulates base content generation"""
    content_types = [
        {"type": "marketing", "tone": "professional", "length": "medium"},
        {"type": "technical", "tone": "formal", "length": "long"},
        {"type": "social", "tone": "casual", "length": "short"}
    ]
    return content_types[int(time.time()) % 3]

def translate_content(content: Dict):
    """Simulates content translation"""
    languages = ["spanish", "french", "german", "japanese", "chinese"]
    translations = {lang: f"Translated content in {lang}" for lang in languages}
    return translations

def check_cultural_context(translations: Dict):
    """Simulates cultural context verification"""
    cultural_issues = {
        "spanish": [],
        "french": ["idiom_mismatch"],
        "german": [],
        "japanese": ["formality_level"],
        "chinese": ["cultural_reference"]
    }
    return cultural_issues

def adapt_content(issues: Dict):
    """Simulates content adaptation"""
    adaptations = {
        "idiom_mismatch": "localized_expression",
        "formality_level": "adjusted_tone",
        "cultural_reference": "localized_reference"
    }
    return {lang: [adaptations[issue] for issue in issues] 
            for lang, issues in issues.items() if issues}

def quality_check():
    """Simulates quality assessment"""
    quality_levels = ["high", "medium", "needs_revision"]
    return quality_levels[int(time.time()) % 3]

# Create specialized agents
content_generator = Agent(
    name="Content Generator",
    role="Base Content Creation",
    goal="Generate high-quality base content",
    instructions="Create engaging base content",
    tools=[generate_base_content]
)

translator = Agent(
    name="Content Translator",
    role="Translation",
    goal="Translate content accurately",
    instructions="Translate content while maintaining meaning",
    tools=[translate_content]
)

cultural_checker = Agent(
    name="Cultural Checker",
    role="Cultural Verification",
    goal="Verify cultural appropriateness",
    instructions="Check for cultural sensitivities",
    tools=[check_cultural_context]
)

content_adapter = Agent(
    name="Content Adapter",
    role="Content Adaptation",
    goal="Adapt content for cultural fit",
    instructions="Modify content based on cultural context",
    tools=[adapt_content]
)

quality_assessor = Agent(
    name="Quality Assessor",
    role="Quality Assessment",
    goal="Ensure content quality",
    instructions="Assess overall content quality",
    tools=[quality_check]
)

# Create workflow tasks
generation_task = Task(
    name="generate_content",
    description="Generate base content",
    expected_output="Base content for translation",
    agent=content_generator,
    is_start=True,
    next_tasks=["translate_content"]
)

translation_task = Task(
    name="translate_content",
    description="Translate content to target languages",
    expected_output="Translated content",
    agent=translator,
    next_tasks=["check_cultural"]
)

cultural_task = Task(
    name="check_cultural",
    description="Check cultural appropriateness",
    expected_output="Cultural context issues",
    agent=cultural_checker,
    next_tasks=["adapt_content"]
)

adaptation_task = Task(
    name="adapt_content",
    description="Adapt content for cultural fit",
    expected_output="Culturally adapted content",
    agent=content_adapter,
    next_tasks=["assess_quality"]
)

quality_task = Task(
    name="assess_quality",
    description="Assess content quality",
    expected_output="Quality assessment",
    agent=quality_assessor,
    task_type="decision",
    condition={
        "high": "",  # Complete workflow
        "medium": ["adapt_content"],  # Minor revisions needed
        "needs_revision": ["translate_content"]  # Major revisions needed
    }
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[content_generator, translator, cultural_checker, 
            content_adapter, quality_assessor],
    tasks=[generation_task, translation_task, cultural_task, 
           adaptation_task, quality_task],
    process="workflow",
    verbose=True
)

def main():
    print("\nStarting Multilingual Content Generation Workflow...")
    print("=" * 50)
    
    # Run workflow
    results = workflow.start()
    
    # Print results
    print("\nContent Generation Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            print(f"\nTask: {task_id}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    main()