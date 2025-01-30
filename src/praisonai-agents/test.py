from typing import List, Dict
from pydantic import BaseModel
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.main import TaskOutput

# Pydantic models for structured output
class Chapter(BaseModel):
    chapter_number: int
    title: str
    outline: str

class StoryOutline(BaseModel):
    title: str
    total_chapters: int
    chapters: List[Chapter]

class ChapterContent(BaseModel):
    chapter_number: int
    title: str
    content: str

# Create the story planner agent
planner_agent = Agent(
    name="Story Planner",
    role="Creative Writing Architect",
    goal="Create detailed story outlines with chapter breakdowns",
    backstory="Expert storyteller skilled in narrative structure and plot development",
    verbose=True,
    llm="gpt-4o-mini",
    self_reflect=False
)

# Create the writer agent
writer_agent = Agent(
    name="Story Writer",
    role="Creative Writer",
    goal="Write engaging and cohesive story chapters",
    backstory="Experienced writer skilled in bringing stories to life with vivid details and engaging narrative",
    verbose=True,
    llm="gpt-4o-mini",
    self_reflect=False
)

# Story title
story_title = "The Curious Cat"

# Step 1: Create outline task
outline_task = Task(
    name="story_outline",
    description=f"""Create a detailed story outline for a story titled '{story_title}'.
    The outline should include:
    1. A compelling story arc
    2. Clear chapter breakdown
    3. Brief description of what happens in each chapter
    4. Character introductions and development points
    
    Provide the response in this exact JSON format:
    {{
        "title": "Story title",
        "total_chapters": number,
        "chapters": [
            {{
                "chapter_number": 1,
                "title": "Chapter title",
                "outline": "Detailed chapter outline"
            }}
        ]
    }}
    """,
    expected_output="Complete story outline",
    agent=planner_agent,
    output_pydantic=StoryOutline
)

# Create initial workflow for outline
outline_workflow = PraisonAIAgents(
    agents=[planner_agent],
    tasks=[outline_task],
    verbose=True,
    process="sequential"
)

# Get the outline
outline_result = outline_workflow.start()
story_outline = outline_result["task_results"][0].pydantic

# Step 2: Create tasks for each chapter
chapter_tasks = []
chapters_content = []

# Create a task for each chapter
for chapter in story_outline.chapters:
    chapter_task = Task(
        name=f"write_chapter_{chapter.chapter_number}",
        description=f"""Write chapter {chapter.chapter_number}: {chapter.title}
        Chapter outline: {chapter.outline}
        
        Write a complete, engaging chapter following this outline.
        Return in this exact JSON format:
        {{
            "chapter_number": {chapter.chapter_number},
            "title": "{chapter.title}",
            "content": "The full chapter content..."
        }}
        """,
        expected_output="Complete chapter content",
        agent=writer_agent,
        output_pydantic=ChapterContent,
        context=[outline_task]
    )
    chapter_tasks.append(chapter_task)

# Create sequential workflow for chapters
chapter_workflow = PraisonAIAgents(
    agents=[writer_agent],
    tasks=chapter_tasks,
    verbose=True,
    process="sequential"
)

# Run the chapter workflow
chapter_results = chapter_workflow.start()

# Collect and validate all chapter contents
for task_result in chapter_results["task_results"].values():
    if task_result and task_result.pydantic:
        chapters_content.append(task_result.pydantic)

# Sort chapters by chapter number
chapters_content.sort(key=lambda x: x.chapter_number)

# Format final result
story = {
    "title": story_outline.title,
    "outline": story_outline.model_dump(),
    "chapters": [chapter.model_dump() for chapter in chapters_content]
}

# Print results
print("\n=== Story Generation Results ===")
print(f"\nTitle: {story['title']}")
print("\nOutline:")
print(story['outline'])
print("\nChapters:")
for chapter in story['chapters']:
    print(f"\nChapter {chapter['chapter_number']}: {chapter['title']}")
    print(chapter['content'][:200] + "...")  # Print first 200 chars of each chapter