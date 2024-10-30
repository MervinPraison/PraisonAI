# tools.py
from duckduckgo_search import DDGS
from praisonai_tools import BaseTool

class InternetSearchTool(BaseTool):
    name: str = "InternetSearchTool"
    description: str = "Search Internet for relevant information based on a query or latest news"

    def _run(self, query: str):
        ddgs = DDGS()
        results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
        return results
    
# Example agent_yaml content

import os
import yaml
from praisonai import PraisonAI

agent_yaml = """
framework: "crewai"
topic: "Job Search Assistance"

roles:
  job_searcher_agent:
    role: "Job Searcher"
    backstory: "You are actively searching for job opportunities in your field, ready to utilize and expand your skill set in a new role."
    goal: "Search for jobs in the field of interest, focusing on enhancing relevant skills."
    tools:
      - "JobSearchTools.search_jobs"
    allow_delegation: true
    tasks:
      job_search_task:
        description: |
          Search for current job openings for the Senior Data Scientist role in New York using the Job Search tool. Find 5 vacant positions in total. Emphasize the key skills required. The tool accepts input in JSON format with the following schema: 'role': '<role>', 'location': '<location>', 'num_results': <number>. Ensure to format the input accordingly.
        expected_output: "A list of 5 Senior Data Scientist job openings in New York, including key skills required for each position."

  skills_development_agent:
    role: "Skills Development Advisor"
    backstory: "As a skills development advisor, you assist job searchers in identifying crucial skills for their target roles and recommend ways to develop these skills."
    goal: "Identify key skills required for jobs of interest and advise on improving them."
    allow_delegation: true
    tasks:
      skills_highlighting_task:
        description: |
          Based on the identified job openings, list the key skills required for each position separately. Provide recommendations on how candidates can acquire or improve these skills through courses, self-study, or practical experience.
        expected_output: "A detailed list of key skills for each position with recommendations on how to develop them."

  interview_preparation_coach:
    role: "Interview Preparation Coach"
    backstory: "Expert in coaching job searchers on successful interview techniques, including mock interviews and feedback."
    goal: "Enhance interview skills, focusing on common questions, presentation, and communication."
    allow_delegation: true
    tasks:
      interview_preparation_task:
        description: |
          Prepare job searchers for interviews by conducting mock interviews and offering feedback on their responses, presentation, and communication skills, for each role separately.
        expected_output: "Feedback and guidance on interview skills for each role, including common questions and tips on presentation and communication."

  career_advisor:
    role: "Career Advisor"
    backstory: "Experienced in guiding candidates through their job search journey, offering personalized advice on career development and application processes."
    goal: "Assist in resume building, LinkedIn profile optimization, and networking strategies."
    allow_delegation: true
    tasks:
      career_advisory_task:
        description: |
          Offer guidance on resume building, optimizing LinkedIn profiles, and effective networking strategies to enhance job application success, for each role separately.
        expected_output: "Personalized advice on resume enhancement, LinkedIn optimization, and networking strategies for each position."

dependencies:
  - task: "skills_highlighting_task"
    depends_on:
      - "job_search_task"
  - task: "interview_preparation_task"
    depends_on:
      - "job_search_task"
  - task: "career_advisory_task"
    depends_on:
      - "job_search_task"
"""

# Create a PraisonAI instance with the agent_yaml content
praisonai = PraisonAI(agent_yaml=agent_yaml)

# Add OPENAI_API_KEY Secrets to Google Colab on the Left Hand Side 🔑 or Enter Manually Below
# os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY') or "ENTER OPENAI_API_KEY HERE"
openai_api_key = os.getenv("OPENAI_API_KEY")

# Run PraisonAI
result = praisonai.run()

# Print the result
print(result)