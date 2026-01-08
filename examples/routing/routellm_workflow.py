"""
RouteLLM Workflow Example

Prerequisites:
1. pip install routellm
2. export OPENAI_API_KEY=your-api-key
3. Start RouteLLM server:
   python -m routellm.openai_server \
     --routers mf \
     --strong-model gpt-4o \
     --weak-model gpt-4o-mini \
     --port 6060
"""

from praisonaiagents import Agent, Workflow

ROUTELLM_URL = "http://localhost:6060/v1"

workflow = Workflow(
    name="Analysis Pipeline",
    steps=[
        Agent(
            name="Analyzer",
            role="Data analyst",
            goal="Analyze data and extract insights",
            llm="router-mf-0.5",
            base_url=ROUTELLM_URL
        ),
        Agent(
            name="Reporter",
            role="Report writer",
            goal="Create clear reports from analysis",
            llm="router-mf-0.5",
            base_url=ROUTELLM_URL
        )
    ]
)

result = workflow.run("Analyze the impact of AI on software development")
print(result["output"])
