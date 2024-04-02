# agents_generator.py

import sys
from .version import __version__
import yaml, os
from rich import print
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
load_dotenv()
import autogen
import gradio as gr
import argparse
from .auto import AutoGenerator
from crewai_tools import *
from .tools import *

class AgentsGenerator:
    def __init__(self, agent_file, framework, config_list):
        self.agent_file = agent_file
        self.framework = framework
        self.config_list = config_list

    def generate_crew_and_kickoff(self):
        if self.agent_file == '/app/api:app' or self.agent_file == 'api:app':
            self.agent_file = 'agents.yaml'
        try:
            with open(self.agent_file, 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"File not found: {self.agent_file}")
            return

        topic = config['topic']
        tools_dict = {
            'CodeDocsSearchTool': CodeDocsSearchTool(),
            'CSVSearchTool': CSVSearchTool(),
            'DirectorySearchTool': DirectorySearchTool(),
            'DOCXSearchTool': DOCXSearchTool(),
            'DirectoryReadTool': DirectoryReadTool(),
            'FileReadTool': FileReadTool(),
            # 'GithubSearchTool': GithubSearchTool(),
            # 'SeperDevTool': SeperDevTool(),
            'TXTSearchTool': TXTSearchTool(),
            'JSONSearchTool': JSONSearchTool(),
            'MDXSearchTool': MDXSearchTool(),
            'PDFSearchTool': PDFSearchTool(),
            # 'PGSearchTool': PGSearchTool(),
            'RagTool': RagTool(),
            'ScrapeElementFromWebsiteTool': ScrapeElementFromWebsiteTool(),
            'ScrapeWebsiteTool': ScrapeWebsiteTool(),
            'WebsiteSearchTool': WebsiteSearchTool(),
            'XMLSearchTool': XMLSearchTool(),
            'YoutubeChannelSearchTool': YoutubeChannelSearchTool(),
            'YoutubeVideoSearchTool': YoutubeVideoSearchTool() 
        }
        # config['tools'] = [tools_dict[tool] for tool in config.get('tools', []) if tool in tools_dict]
        framework = self.framework or config.get('framework')

        agents = {}
        tasks = []
        if framework == "autogen":
            # Load the LLM configuration dynamically
            # print(self.config_list)
            llm_config = {"config_list": self.config_list}
            
            # Assuming the user proxy agent is set up as per your requirements
            user_proxy = autogen.UserProxyAgent(
                name="User",
                human_input_mode="NEVER",
                is_termination_msg=lambda x: (x.get("content") or "").rstrip().rstrip(".").lower().endswith("terminate") or "TERMINATE" in (x.get("content") or ""),
                code_execution_config={
                    "work_dir": "coding",
                    "use_docker": False,
                },
                # additional setup for the user proxy agent
            )
            
            for role, details in config['roles'].items():
                agent_name = details['role'].format(topic=topic).replace("{topic}", topic)
                agent_goal = details['goal'].format(topic=topic)
                # Creating an AssistantAgent for each role dynamically
                agents[role] = autogen.AssistantAgent(
                    name=agent_name,
                    llm_config=llm_config,
                    system_message=details['backstory'].format(topic=topic)+". Must Reply \"TERMINATE\" in the end when everything is done.",
                )
                for tool in details.get('tools', []):
                    if tool in tools_dict:
                        tool_class = globals()[f'autogen_{type(tools_dict[tool]).__name__}']
                        tool_class(agents[role], user_proxy)

                # Preparing tasks for initiate_chats
                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = task_details['description'].format(topic=topic)
                    expected_output_filled = task_details['expected_output'].format(topic=topic)
                    
                    chat_task = {
                        "recipient": agents[role],
                        "message": description_filled,
                        "summary_method": "last_msg", 
                        # Additional fields like carryover can be added based on dependencies
                    }
                    tasks.append(chat_task)

            response = user_proxy.initiate_chats(tasks)
            result = "### Output ###\n"+response[-1].summary if hasattr(response[-1], 'summary') else ""
        else:
            for role, details in config['roles'].items():
                role_filled = details['role'].format(topic=topic)
                goal_filled = details['goal'].format(topic=topic)
                backstory_filled = details['backstory'].format(topic=topic)
                
                # Adding tools to the agent if exists
                agent_tools = [tools_dict[tool] for tool in details.get('tools', []) if tool in tools_dict]
                agent = Agent(role=role_filled, goal=goal_filled, backstory=backstory_filled, tools=agent_tools, allow_delegation=False)
                agents[role] = agent

                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = task_details['description'].format(topic=topic)
                    expected_output_filled = task_details['expected_output'].format(topic=topic)

                    task = Task(description=description_filled, expected_output=expected_output_filled, agent=agent)
                    tasks.append(task)
            # print(agents)
            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=2
            )

            response = crew.kickoff()
            result = f"### Task Output ###\n{response}"
        return result
    

# # AutoGen Tools example below
# from typing import Any, Optional
# import os
# from autogen import ConversableAgent
# from autogen_tools import autogen_ScrapeWebsiteTool

# assistant = ConversableAgent(
#     name="Assistant",
#     system_message="You are a helpful AI assistant. "
#     "You can help with website scraping. "
#     "Return 'TERMINATE' when the task is done.",
#     llm_config={"config_list": [{"model": "gpt-3.5-turbo", "api_key": os.environ["OPENAI_API_KEY"]}]},
# )

# user_proxy = ConversableAgent(
#     name="User",
#     llm_config=False,
#     is_termination_msg=lambda msg: msg.get("content") is not None and "TERMINATE" in msg["content"],
#     human_input_mode="NEVER",
# )

# autogen_ScrapeWebsiteTool(assistant, user_proxy)

# chat_result = user_proxy.initiate_chat(assistant, message="Scrape the official Nodejs website.")

# # CrewAI Tools example below 
# import os
# from crewai import Agent, Task, Crew
# # Importing crewAI tools
# from crewai_tools import (
#     DirectoryReadTool,
#     FileReadTool,
#     SerperDevTool,
#     WebsiteSearchTool
# )

# # Set up API keys
# os.environ["SERPER_API_KEY"] = "Your Key" # serper.dev API key
# os.environ["OPENAI_API_KEY"] = "Your Key"

# # Instantiate tools
# docs_tool = DirectoryReadTool(directory='./blog-posts')
# file_tool = FileReadTool()
# search_tool = SerperDevTool()
# web_rag_tool = WebsiteSearchTool()

# # Create agents
# researcher = Agent(
#     role='Market Research Analyst',
#     goal='Provide up-to-date market analysis of the AI industry',
#     backstory='An expert analyst with a keen eye for market trends.',
#     tools=[search_tool, web_rag_tool],
#     verbose=True
# )

# writer = Agent(
#     role='Content Writer',
#     goal='Craft engaging blog posts about the AI industry',
#     backstory='A skilled writer with a passion for technology.',
#     tools=[docs_tool, file_tool],
#     verbose=True
# )

# # Define tasks
# research = Task(
#     description='Research the latest trends in the AI industry and provide a summary.',
#     expected_output='A summary of the top 3 trending developments in the AI industry with a unique perspective on their significance.',
#     agent=researcher
# )

# write = Task(
#     description='Write an engaging blog post about the AI industry, based on the research analyst’s summary. Draw inspiration from the latest blog posts in the directory.',
#     expected_output='A 4-paragraph blog post formatted in markdown with engaging, informative, and accessible content, avoiding complex jargon.',
#     agent=writer,
#     output_file='blog-posts/new_post.md'  # The final blog post will be saved here
# )

# # Assemble a crew
# crew = Crew(
#     agents=[researcher, writer],
#     tasks=[research, write],
#     verbose=2
# )

# # Execute tasks
# crew.kickoff()