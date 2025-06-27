# ===============================
# 1. 📘 Project Title & Purpose
# ===============================
# """
# AI‑Powered Personalized Learning Assistant with Smart Content Chatbot

# This assistant helps users learn any topic by chatting with an AI tutor. 
# It uses PraisonAI Agents, OpenAI API, and Transformers to deliver answers clearly.
# """

# ============================
# 2. 📦 Dependencies Required
# ============================
# """
# Required Libraries:
# - praisonaiagents
# - openai
# - transformers

# Make sure to install these in Colab or terminal:
# !pip install praisonaiagents openai transformers
# """

# =====================
# 3. 🧰 Tools Used
# =====================
# """
# ✅ praisonaiagents – Builds the smart tutoring agent  
# ✅ openai – Uses OpenAI GPT for accurate answers  
# ✅ transformers – Fallback model using GPT-2  
# ✅ Python I/O – Simple interactive CLI using input/print
# """

# ============================
# 4. 🔐 Set OpenAI API Key
# ============================
import os
os.environ['OPENAI_API_KEY'] = input('Enter your OpenAI API key: ')

# ================================
# 5. 🧠 Initialize AI Agent + Fallback
# ================================
from praisonaiagents import Agent
from transformers import pipeline as hf_pipeline
import openai

openai.api_key = os.getenv('OPENAI_API_KEY')
hf_chatbot = hf_pipeline('text-generation', model='gpt2')

agent = Agent(instructions='You are a friendly tutor. Answer learner questions clearly and helpfully.')

def chat_with_ai(user_input):
    try:
        return agent.start(user_input)
    except Exception as e:
        print('[Fallback GPT-2]', e)
        return hf_chatbot(user_input, max_length=100)[0]['generated_text']

# ============================
# 6. 💬 Interactive Chat Loop
# ============================
print("Start chatting with your AI tutor! Type 'exit' to quit.")
while True:
    user_input = input('You: ')
    if user_input.lower() in ['exit', 'quit']:
        print('Goodbye! Happy learning!')
        break
    response = chat_with_ai(user_input)
    print('🤖 Tutor:', response)
