from praisonaiagents import Agent, Task, PraisonAIAgents

# Create PDF Analysis Agent
pdf_agent = Agent(
    name="PDFAnalyst",
    role="PDF Document Specialist",
    goal="Analyze PDF documents to extract meaningful information",
    backstory="""You are an expert in PDF document analysis and text extraction.
    You excel at understanding document structure, extracting content, and analyzing textual information.""",
    llm="gpt-4o-mini",
    self_reflect=False
)

# 1. Task with PDF URL
task1 = Task(
    name="analyze_pdf_url",
    description="Extract and analyze content from this PDF document.",
    expected_output="Detailed analysis of the PDF content and structure",
    agent=pdf_agent,
    input=["https://example.com/document.pdf"]
)

# 2. Task with Local PDF File
task2 = Task(
    name="analyze_local_pdf",
    description="What information can you extract from this PDF? Analyze its content.",
    expected_output="Detailed analysis of the PDF content and structure",
    agent=pdf_agent,
    input=["document.pdf"] 
)

# Create PraisonAIAgents instance
agents = PraisonAIAgents(
    agents=[pdf_agent],
    tasks=[task1, task2],
    process="sequential",
    verbose=1
)

# Run all tasks
agents.start()