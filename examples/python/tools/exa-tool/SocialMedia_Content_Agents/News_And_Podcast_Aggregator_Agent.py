#!/usr/bin/env python
# coding: utf-8

# # News and Podcast Aggregator Agent using PraisonAIAgents

# This notebook demonstrates a News and Podcast Aggregator Agent built with `praisonaiagents`.  
# It summarizes news articles and generates podcast-style discussion points.  
# The notebook is CI-friendly: it uses dummy data if API keys are not set, so all tests/checks will pass.

# [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Dhivya-Bharathy/PraisonAI/blob/main/examples/cookbooks/SocialMedia_Content_Agents/News_And_Podcast_Aggregator_Agent.ipynb)
# 

# # Dependencies

# In[ ]:


get_ipython().system('pip install praisonaiagents pydantic')


# # Imports and Setup

# In[3]:


import os

# Set up the OpenAI API key for praisonaiagents
os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "sk-..")

def is_valid_key(key, prefix):
    return key and key != f"{prefix}-.." and key.startswith(prefix)

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]


# # Tools

# In[4]:


from datetime import datetime
from typing import List

def format_search_results_for_podcast(search_results: List[dict]) -> tuple[str, List[str]]:
    """
    Custom tool to format search results for podcast script generation.
    """
    created_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    structured_content = []
    structured_content.append(f"PODCAST CREATION: {created_at}\n")
    sources = []
    for idx, search_result in enumerate(search_results):
        try:
            if search_result.get("confirmed", False):
                sources.append(search_result["url"])
                structured_content.append(
                    f"""
                    SOURCE {idx + 1}:
                    Title: {search_result['title']}
                    URL: {search_result['url']}
                    Content: {search_result.get('full_text') or search_result.get('description', '')}
                    ---END OF SOURCE {idx + 1}---
                    """.strip()
                )
        except Exception as e:
            print(f"Error processing search result: {e}")
    content_texts = "\n\n".join(structured_content)
    return content_texts, sources


# # Pydantic Models

# In[5]:


from pydantic import BaseModel, Field
from typing import List, Optional

class Dialog(BaseModel):
    speaker: str = Field(..., description="The speaker name (SHOULD BE 'ALEX' OR 'MORGAN')")
    text: str = Field(..., description="The spoken text content for this speaker based on the requested language, default is English")

class Section(BaseModel):
    type: str = Field(..., description="The section type (intro, headlines, article, outro)")
    title: Optional[str] = Field(None, description="Optional title for the section (required for article type)")
    dialog: List[Dialog] = Field(..., description="List of dialog exchanges between speakers")

class PodcastScript(BaseModel):
    title: str = Field(..., description="The podcast episode title with date")
    sections: List[Section] = Field(..., description="List of podcast sections (intro, headlines, articles, outro)")


# # Agent Instructions

# In[6]:


from textwrap import dedent

PODCAST_AGENT_DESCRIPTION = "You are a helpful assistant that can generate engaging podcast scripts for the given sources."
PODCAST_AGENT_INSTRUCTIONS = dedent("""
    You are a helpful assistant that can generate engaging podcast scripts for the given source content and query.
    For given content, create an engaging podcast script that should be at least 15 minutes worth of content and you are allowed to enhance the script beyond given sources if you know something additional info will be interesting to the discussion or not enough content is available.
    You use the provided sources to ground your podcast script generation process. Keep it engaging and interesting.
    IMPORTANT: Generate the entire script in the provided language.
    CONTENT GUIDELINES:
    - Provide insightful analysis that helps the audience understand the significance
    - Include discussions on potential implications and broader context of each story
    - Explain complex concepts in an accessible but thorough manner
    - Make connections between current and relevant historical developments when applicable
    - Provide comparisons and contrasts with similar stories or trends when relevant
    PERSONALITY NOTES:
    - Alex is more analytical and fact-focused
    - Morgan is more focused on human impact, social context, and practical applications
    - Include natural, conversational banter and smooth transitions between topics
    - Each article discussion should go beyond the basic summary to provide valuable insights
    - Maintain a conversational but informed tone that would appeal to a general audience
    IMPORTANT:
        - MAKE SURE PODCAST SCRIPTS ARE AT LEAST 15 MINUTES LONG WHICH MEANS YOU NEED TO HAVE DETAILED DISCUSSIONS BUT KEEP IT INTERESTING AND ENGAGING.
""")


# # Dummy Data and Main Logic

# In[7]:


from praisonaiagents import Agent

# Dummy search results for CI/public use
dummy_search_results = [
    {
        "confirmed": True,
        "title": "AI Revolutionizes Healthcare",
        "url": "https://news.example.com/ai-healthcare",
        "full_text": "Artificial intelligence is transforming the healthcare industry by..."
    },
    {
        "confirmed": True,
        "title": "Climate Change and Global Policy",
        "url": "https://news.example.com/climate-policy",
        "full_text": "World leaders are meeting to discuss new policies for climate change..."
    }
]

query = "Latest technology and world news"
language_name = "English"

content_texts, sources = format_search_results_for_podcast(dummy_search_results)

if not is_valid_key(OPENAI_API_KEY, "sk"):
    print("API key not set or is a placeholder. Using dummy podcast script for CI/testing.")
    print("=== Podcast Script ===")
    print(f"Podcast Title: Tech & World News Roundup ({datetime.now().strftime('%B %d, %Y')})")
    for idx, article in enumerate(dummy_search_results):
        print(f"\nSection {idx+1}: {article['title']}")
        print(f"Summary: {article['full_text'][:80]}...")
else:
    agent = Agent(
        name="Podcast Script Agent",
        instructions=PODCAST_AGENT_INSTRUCTIONS,
        api_key=OPENAI_API_KEY
    )
    prompt = f"query: {query}\nlanguage_name: {language_name}\ncontent_texts: {content_texts}\nIMPORTANT: texts should be in {language_name} language."
    podcast_script = agent.start(prompt)
    print("=== Podcast Script ===")
    print(podcast_script)

