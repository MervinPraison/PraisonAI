# Docs: https://docs.crewai.com/en/concepts/crews
import os

from crewai import LLM, Agent, Crew, Process, Task

URL = os.environ["BENCH_STUB_URL"] + "/v1"  # bench:config


def build():
    llm = LLM(model="openai/gpt-4o-mini", base_url=URL)
    researcher = Agent(role="Researcher", goal="Research the topic.", backstory="Researcher", llm=llm)
    writer = Agent(role="Writer", goal="Write a draft from the research.", backstory="Writer", llm=llm)
    editor = Agent(role="Editor", goal="Edit the draft.", backstory="Editor", llm=llm)
    return Crew(
        agents=[researcher, writer, editor],
        tasks=[
            Task(description="Research {topic}.", expected_output="Notes", agent=researcher),
            Task(description="Write a draft.", expected_output="A draft", agent=writer),
            Task(description="Edit the draft.", expected_output="The final text", agent=editor),
        ],
        process=Process.sequential,
    )


def run(crew):
    return crew.kickoff(inputs={"topic": "AI agents"}).raw
