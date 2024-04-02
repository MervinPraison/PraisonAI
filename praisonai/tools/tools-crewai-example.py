
import os
from crewai import Agent, Task, Crew
from crewai_tools import (
    DirectoryReadTool,
    FileReadTool,
    SerperDevTool,
    WebsiteSearchTool
)

os.environ["SERPER_API_KEY"] = "Your Key"
os.environ["OPENAI_API_KEY"] = "Your Key"

docs_tool = DirectoryReadTool(directory='./blog-posts')
file_tool = FileReadTool()
search_tool = SerperDevTool()
web_rag_tool = WebsiteSearchTool()

researcher = Agent(
    role='Market Research Analyst',
    goal='Provide up-to-date market analysis of the AI industry',
    backstory='An expert analyst with a keen eye for market trends.',
    tools=[search_tool, web_rag_tool],
    verbose=True
)

writer = Agent(
    role='Content Writer',
    goal='Craft engaging blog posts about the AI industry',
    backstory='A skilled writer with a passion for technology.',
    tools=[docs_tool, file_tool],
    verbose=True
)

research = Task(
    description='Research the latest trends in the AI industry and provide a summary.',
    expected_output='A summary of the top 3 trending developments in the AI industry with a unique perspective on their significance.',
    agent=researcher
)

write = Task(
    description='Write an engaging blog post about the AI industry, based on the research analyst\'s summary. Draw inspiration from the latest blog posts in the directory.',
    expected_output='A 4-paragraph blog post formatted in markdown with engaging, informative, and accessible content, avoiding complex jargon.',
    agent=writer,
    output_file='blog-posts/new_post.md'
)

crew = Crew(
    agents=[researcher, writer],
    tasks=[research, write],
    verbose=2
)

crew.kickoff()

from crewai_tools import DirectoryReadTool

tool = DirectoryReadTool()

toos = DirectoryReadTool(directory='./directory')

from crewai_tools import BaseTool

class MyCustomTool(BaseTool):
    name: str = "Name of my tool"
    description: str = "Clear description for what this tool is useful for, you agent will need this information to use it."

    def _run(self, argument: str) -> str:
        return "Result from custom tool"

from crewai_tools import tool

@tool("Name of my tool")
def my_tool(question: str) -> str:
    return "Result from my tool"

import json
import requests
from crewai import Agent
from crewai.tools import tool
from unstructured.partition.html import partition_html

@tool("Integration with a given API")
def integration_tool(argument: str) -> str:
    return "Results from integration tool"

agent = Agent(
    role='Research Analyst',
    goal='Provide up-to-date market analysis',
    backstory='An expert analyst with a keen eye for market trends.',
    tools=[integration_tool]
)

from crewai import Agent
from langchain.agents import Tool
from langchain.utilities import GoogleSerperAPIWrapper

os.environ["SERPER_API_KEY"] = "Your Key"

search = GoogleSerperAPIWrapper()

serper_tool = Tool(
  name="Intermediate Answer",
  func=search.run,
  description="Useful for search-based queries",
)

agent = Agent(
  role='Research Analyst',
  goal='Provide up-to-date market analysis',
  backstory='An expert analyst with a keen eye for market trends.',
  tools=[serper_tool]
)
# Tool	Description
# CodeDocsSearchTool	A RAG tool optimized for searching through code documentation and related technical documents.
# CSVSearchTool	A RAG tool designed for searching within CSV files, tailored to handle structured data.
# DirectorySearchTool	A RAG tool for searching within directories, useful for navigating through file systems.
# DOCXSearchTool	A RAG tool aimed at searching within DOCX documents, ideal for processing Word files.
# DirectoryReadTool	Facilitates reading and processing of directory structures and their contents.
# FileReadTool	Enables reading and extracting data from files, supporting various file formats.
# GithubSearchTool	A RAG tool for searching within GitHub repositories, useful for code and documentation search.
# SeperDevTool	A specialized tool for development purposes, with specific functionalities under development.
# TXTSearchTool	A RAG tool focused on searching within text (.txt) files, suitable for unstructured data.
# JSONSearchTool	A RAG tool designed for searching within JSON files, catering to structured data handling.
# MDXSearchTool	A RAG tool tailored for searching within Markdown (MDX) files, useful for documentation.
# PDFSearchTool	A RAG tool aimed at searching within PDF documents, ideal for processing scanned documents.
# PGSearchTool	A RAG tool optimized for searching within PostgreSQL databases, suitable for database queries.
# RagTool	A general-purpose RAG tool capable of handling various data sources and types.
# ScrapeElementFromWebsiteTool	Enables scraping specific elements from websites, useful for targeted data extraction.
# ScrapeWebsiteTool	Facilitates scraping entire websites, ideal for comprehensive data collection.
# WebsiteSearchTool	A RAG tool for searching website content, optimized for web data extraction.
# XMLSearchTool	A RAG tool designed for searching within XML files, suitable for structured data formats.
# YoutubeChannelSearchTool	A RAG tool for searching within YouTube channels, useful for video content analysis.
# YoutubeVideoSearchTool	A RAG tool aimed at searching within YouTube videos, ideal for video data extraction.
