"""Direct LiteLLM test to compare with PraisonAI behavior"""
import os
from dotenv import load_dotenv
load_dotenv("/Users/praison/praisonai-package/src/praisonai-agents/.env")

# Debug: print the API key
api_key = os.environ.get('GEMINI_API_KEY', 'NOT SET')
print(f"GEMINI_API_KEY loaded: {api_key[:20]}...")

import litellm
litellm.drop_params = True  # Drop unsupported params like seed

from litellm import completion

# Same config as the agent test - pass api_key explicitly
response = completion(
    model="gemini/gemini-3-flash-preview",
    messages=[
        {"role": "system", "content": "You are a helpful Assistant specialized in scientific explanations. Provide clear, accurate, and engaging responses."},
        {"role": "user", "content": "Why is the sky blue? Please explain in simple terms."}
    ],
    temperature=0.7,
    max_tokens=1000,
    top_p=0.9,
    api_key=api_key,
    # stop=["##", "END"]  # Removed - may cause truncation
)

print("=" * 80)
print("DIRECT LITELLM RESPONSE:")
print("=" * 80)
print(response.choices[0].message.content)
print("=" * 80)
print(f"Finish reason: {response.choices[0].finish_reason}")
print(f"Usage: {response.usage}")
