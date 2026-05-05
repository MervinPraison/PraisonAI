"""
CAJAL Scientific Writer Agent Example

This example demonstrates how to use the ScientificWriterAgent with CAJAL model
for generating academic papers in LaTeX format.

CAJAL is a specialized 2GB local model for scientific paper generation,
part of the P2PCLAW decentralized research network.

Example Usage:
    python cajal_integration_example.py
"""

import sys
import os

# Add the src directory to Python path for examples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

from praisonaiagents import ScientificWriterAgent, Agent, AgentTeam, Task

def basic_scientific_writing_example():
    """Basic example of using ScientificWriterAgent with CAJAL."""
    
    print("=== Basic Scientific Writing Example ===")
    
    # Create a scientific writer agent using CAJAL model
    scientific_writer = ScientificWriterAgent(
        name="Research Paper Writer",
        model="Agnuxo/CAJAL-4B-P2PCLAW",  # HuggingFace model path
        instructions="You are a specialized scientific paper writer trained on academic literature."
    )
    
    # Generate a scientific paper
    topic = "Climate Change Effects on Coral Reef Ecosystems"
    print(f"Generating scientific paper on: {topic}")
    
    paper = scientific_writer.write_paper(
        topic=topic,
        sections=["Introduction", "Literature Review", "Methodology", "Results", "Discussion", "Conclusion"],
        style="academic",
        citation_style="APA"
    )
    
    print(f"Generated paper: {paper.title}")
    print(f"Number of sections: {len(paper.sections)}")
    print(f"Number of references: {len(paper.references)}")
    
    # Display a section
    if paper.sections:
        print(f"\nFirst section preview:")
        print(f"Title: {paper.sections[0].title}")
        print(f"Content: {paper.sections[0].content[:200]}...")
    
    return paper

def multi_agent_scientific_workflow_example():
    """Example of multi-agent scientific writing workflow."""
    
    print("\n=== Multi-Agent Scientific Workflow Example ===")
    
    # Create specialized agents for different research tasks
    literature_reviewer = Agent(
        name="Literature Reviewer",
        role="Literature Review Specialist", 
        instructions="You specialize in reviewing scientific literature and identifying key research gaps.",
        model="gpt-4o-mini"  # Use default model for literature review
    )
    
    methodology_designer = Agent(
        name="Methodology Designer",
        role="Research Methodology Expert",
        instructions="You design rigorous research methodologies for scientific studies.",
        model="gpt-4o-mini"
    )
    
    scientific_writer = ScientificWriterAgent(
        name="Scientific Writer",
        model="Agnuxo/CAJAL-4B-P2PCLAW"  # Use CAJAL for specialized scientific writing
    )
    
    # Create tasks for the workflow
    review_task = Task(
        name="review_literature",
        description="Review existing literature on coral reef climate impacts",
        agent=literature_reviewer
    )
    
    methodology_task = Task(
        name="design_methodology", 
        description="Design a methodology for studying coral reef responses to climate change",
        agent=methodology_designer
    )
    
    writing_task = Task(
        name="write_paper",
        description="Write a comprehensive scientific paper combining literature review and methodology",
        agent=scientific_writer
    )
    
    # Create the research team
    research_team = AgentTeam(
        agents=[literature_reviewer, methodology_designer, scientific_writer],
        tasks=[review_task, methodology_task, writing_task]
    )
    
    print("Executing multi-agent research workflow...")
    
    # Execute the workflow (this would run all tasks)
    # Note: In a real implementation, tasks would be executed sequentially
    # with outputs passed between agents
    
    # For this example, demonstrate individual agent capabilities
    print("\n1. Literature Review Agent:")
    literature_result = literature_reviewer.start("Review key literature on coral reef climate impacts")
    print(f"Literature review: {literature_result[:100]}...")
    
    print("\n2. Methodology Designer Agent:")
    methodology_result = methodology_designer.start("Design a methodology for coral reef climate study")
    print(f"Methodology: {methodology_result[:100]}...")
    
    print("\n3. Scientific Writer Agent (CAJAL):")
    paper_section = scientific_writer.write_section(
        section_title="Introduction",
        content_request="Write an introduction combining the literature review and methodology",
        context=f"Literature: {literature_result}\nMethodology: {methodology_result}"
    )
    print(f"Introduction section: {paper_section.content[:100]}...")
    
    return research_team

def specialized_scientific_tasks_example():
    """Example of specialized scientific writing tasks."""
    
    print("\n=== Specialized Scientific Tasks Example ===")
    
    scientific_writer = ScientificWriterAgent(
        name="Academic Writer",
        model="Agnuxo/CAJAL-4B-P2PCLAW"
    )
    
    # Generate different types of scientific content
    
    # 1. Literature review with citations
    print("1. Generating literature review with citations...")
    literature_review = scientific_writer.review_and_cite(
        research_query="machine learning applications in climate science",
        existing_content="Machine learning has emerged as a powerful tool for climate research."
    )
    print(f"Literature review: {literature_review[:150]}...")
    
    # 2. Methodology section
    print("\n2. Generating methodology section...")
    methodology = scientific_writer.write_section(
        section_title="Methodology",
        content_request="Describe a machine learning methodology for climate data analysis"
    )
    print(f"Methodology: {methodology.content[:150]}...")
    
    # 3. Results section with LaTeX formatting
    print("\n3. Generating results section...")
    results = scientific_writer.write_section(
        section_title="Results",
        content_request="Present hypothetical results with statistical analysis and LaTeX formatting"
    )
    print(f"Results: {results.content[:150]}...")
    
    return scientific_writer

def main():
    """Run all examples."""
    
    print("CAJAL Scientific Writer Agent Integration Examples")
    print("=" * 60)
    print("\nCAJAL Model Information:")
    print("- Model: Agnuxo/CAJAL-4B-P2PCLAW (HuggingFace)")
    print("- Size: 2GB local model")
    print("- Specialization: Scientific paper generation")
    print("- Output: LaTeX-formatted academic content")
    print("- Part of: P2PCLAW decentralized research network")
    
    # Run examples
    try:
        # Example 1: Basic scientific writing
        paper = basic_scientific_writing_example()
        
        # Example 2: Multi-agent workflow
        team = multi_agent_scientific_workflow_example()
        
        # Example 3: Specialized tasks
        writer = specialized_scientific_tasks_example()
        
        print("\n=== Integration Success ===")
        print("✅ ScientificWriterAgent successfully integrated with PraisonAI")
        print("✅ CAJAL model support implemented")
        print("✅ Multi-agent scientific workflows enabled")
        print("✅ LaTeX formatting capabilities added")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        print("Note: This example requires CAJAL model to be available.")
        print("Install with: pip install transformers torch")

if __name__ == "__main__":
    main()