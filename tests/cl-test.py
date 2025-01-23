import os
import chainlit as cl
import google.generativeai as genai
from typing import List, Optional, Dict, Any, Union, Literal, Type
from pydantic import BaseModel
import json

# Configure the Gemini API
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Define generation configuration
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

def read_system_instructions():
    try:
        with open("/Users/praison/praisonai-package/.cursorrules", "r") as file:
            return file.read()
    except Exception as e:
        print(f"Error reading .cursorrules file: {e}")
        return ""

def read_current_file():
    try:
        with open("/Users/praison/praisonai-package/praisonai/test.py", "r") as file:
            return file.read()
    except Exception as e:
        print(f"Error reading test.py file: {e}")
        return ""

# Create the GenerativeModel instance with system instructions
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-exp",
    generation_config=generation_config,
    system_instruction=read_system_instructions(),
)

@cl.on_chat_start
async def start():
    # Initialize chat session
    chat = model.start_chat(history=[])
    
    # Store chat in user session
    cl.user_session.set("chat", chat)

@cl.on_message
async def main(message: str):
    # Retrieve chat session
    chat = cl.user_session.get("chat")
    
    # Append current file content to user message
    file_content = read_current_file()
    full_message = f"""
Current file:
{file_content}

User message:
{message}
"""
    
    # Send message and get streaming response
    response = chat.send_message(full_message, stream=True)

    # Create message placeholder for streaming
    msg = cl.Message(content="")
    
    # Stream the response token by token
    for chunk in response:
        await msg.stream_token(chunk.text)

    # Send final message
    await msg.send()

@cl.on_chat_end
def end():
    print("Chat ended")

# Error handling for missing files
@cl.on_stop
def on_stop():
    print("Stopped by user")

if __name__ == "__main__":
    # Verify system files exist
    if not os.path.exists("/Users/praison/praisonai-package/.cursorrules"):
        print("Warning: .cursorrules file not found")
    if not os.path.exists("/Users/praison/praisonai-package/praisonai/test.py"):
        print("Warning: test.py file not found")