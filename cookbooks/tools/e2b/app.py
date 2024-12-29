from praisonaiagents import Agent, Task, PraisonAIAgents, error_logs
import json
from e2b_code_interpreter import Sandbox

def code_interpret(code: str):
    """
    A function to demonstrate running Python code dynamically using e2b_code_interpreter.
    """
    print(f"\n{'='*50}\n> Running following AI-generated code:\n{code}\n{'='*50}")
    exec_result = Sandbox().run_code(code)
    if exec_result.error:
        print("[Code Interpreter error]", exec_result.error)
        return {"error": str(exec_result.error)}
    else:
        results = []
        for result in exec_result.results:
            if hasattr(result, '__iter__'):
                results.extend(list(result))
            else:
                results.append(str(result))
        logs = {"stdout": list(exec_result.logs.stdout), "stderr": list(exec_result.logs.stderr)}
        return json.dumps({"results": results, "logs": logs})

# 1) Create Agents
web_scraper_agent = Agent(
    name="WebScraper",
    role="Web Scraper",
    goal="Extract URLs from https://quotes.toscrape.com/",
    backstory="An expert in data extraction from websites, adept at navigating and retrieving detailed information.",
    tools=[code_interpret],
    llm="gpt-4o"
)

url_data_extractor_agent = Agent(
    name="URLDataExtractor",
    role="URL Data Extractor",
    goal="Crawl each URL for data extraction",
    backstory="Specializes in crawling websites to gather comprehensive data, ensuring nothing is missed from each link.",
    tools=[code_interpret],
    llm="gpt-4o"
)

blog_writer_agent = Agent(
    name="BlogWriter",
    role="Creative Content Writer",
    goal="Create engaging and insightful blog posts from provided data",
    backstory="An experienced content creator and storyteller with a knack for weaving compelling narratives. Skilled at analyzing quotes and creating meaningful connections that resonate with readers.",
    tools=[code_interpret],
    llm="gpt-4o"
)

# 2) Create Tasks
task_url_extraction = Task(
    name="url_extraction_task",
    description="""Use code_interpret to run Python code that fetches https://quotes.toscrape.com/
    and extracts 5 URLs from the page, then outputs them as a list. Only first 5 urls""",
    expected_output="A list of URLs extracted from the source page.",
    agent=web_scraper_agent,
    output_file="urls.txt" 
)

task_data_extraction = Task(
    name="data_extraction_task",
    description="""Take the URLs from url_extraction_task, crawl each URL and extract all pertinent
    data using code_interpret to run Python code, then output raw txt, not the html.""",
    expected_output="Raw data collected from each crawled URL.",
    agent=url_data_extractor_agent,
    context=[task_url_extraction]
)

blog_writing_task = Task(
    name="blog_writing_task",
    description="""Write an engaging blog post using the extracted quotes data. The blog post should:
    1. Have a catchy title
    2. Include relevant quotes from the data
    3. Provide commentary and insights about the quotes
    4. Be well-structured with introduction, body, and conclusion
    5. Be approximately 500 words long""",
    expected_output="A well-written blog post incorporating the extracted quotes with analysis",
    agent=blog_writer_agent,
    context=[task_data_extraction],
    output_file="blog_post.txt"  
)

# 3) Create and run Agents manager
agents_manager = PraisonAIAgents(
    agents=[web_scraper_agent, url_data_extractor_agent, blog_writer_agent],
    tasks=[task_url_extraction, task_data_extraction, blog_writing_task],
    verbose=True,
    process="hierarchical",
    manager_llm="gpt-4o"
)

result = agents_manager.start()