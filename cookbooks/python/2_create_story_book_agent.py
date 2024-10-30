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
from praisonai import PraisonAI

agent_yaml = """
framework: "crewai"
topic: "Children's Storybook Creation"
roles:
  story_outliner:
    role: "Story Outliner"
    backstory: "An imaginative creator who lays the foundation of captivating stories for children."
    goal: "Develop an outline for a children's storybook about Animals, including chapter titles and characters for 5 chapters."
    tasks:
      task_outline:
        description: "Create an outline for the children's storybook about Animals, detailing chapter titles and character descriptions for 5 chapters."
        expected_output: "A structured outline document containing 5 chapter titles, with detailed character descriptions and the main plot points for each chapter."
    tools:
      - InternetSearchTool
  story_writer:
    role: "Story Writer"
    backstory: "A talented storyteller who brings to life the world and characters outlined, crafting engaging and imaginative tales for children."
    goal: "Write the full content of the story for all 5 chapters, each chapter 100 words, weaving together the narratives and characters outlined."
    tasks:
      task_write:
        description: "Using the outline provided, write the full story content for all chapters, ensuring a cohesive and engaging narrative for children. Each chapter should contain approximately 100 words. Include the title of the story at the top."
        expected_output: "A complete manuscript of the children's storybook about Animals with 5 chapters, each approximately 100 words, following the provided outline and integrating the characters and plot points into a cohesive narrative."
  image_generator:
    role: "Image Generator"
    backstory: "A creative AI specialized in visual storytelling, bringing each chapter to life through imaginative imagery."
    goal: "Generate one image per chapter based on the content provided by the story writer. Start with chapter number, chapter content, character details, detailed location information, and detailed items in the location where the activity happens. Generate a total of 5 images one by one. Final output should contain all 5 images in JSON format."
    tasks:
      task_image_generate:
        description: "Generate 5 images that capture the essence of the children's storybook about Animals, aligning with the themes, characters, and narratives outlined in the chapters. Do it one by one."
        expected_output: "A set of digital images that visually represent each chapter of the children's storybook, incorporating elements from the characters and plot as described in the chapters. The images should be suitable for inclusion in the storybook as illustrations."
  content_formatter:
    role: "Content Formatter"
    backstory: "A meticulous formatter who enhances the readability and presentation of the storybook."
    goal: "Format the written story content in markdown, including images at the beginning of each chapter."
    tasks:
      task_format_content:
        description: "Format the story content in markdown, including an image at the beginning of each chapter."
        expected_output: "The entire storybook content formatted in markdown, with each chapter title followed by the corresponding image and the chapter content."
        output_file: "story.md"
  markdown_to_pdf_creator:
    role: "PDF Converter"
    backstory: "An efficient converter that transforms Markdown files into professionally formatted PDF documents."
    goal: "Convert the Markdown file to a PDF document. 'story.md' is the markdown file name."
    tasks:
      task_markdown_to_pdf:
        description: "Convert a Markdown file to a PDF document, ensuring the preservation of formatting, structure, and embedded images using the mdpdf library."
        expected_output: "A PDF file generated from the Markdown input, accurately reflecting the content with proper formatting. The PDF should be ready for sharing or printing."

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