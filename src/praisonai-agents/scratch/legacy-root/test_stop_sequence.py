"""Test to verify stop sequence issue with Gemini"""
import os
from dotenv import load_dotenv
load_dotenv("/Users/praison/praisonai-package/src/praisonai-agents/.env")

api_key = os.environ.get('GEMINI_API_KEY')

import litellm
litellm.drop_params = True

from litellm import completion

# Test 1: With stop=["##"]
print("=" * 80)
print("TEST 1: With stop=['##']")
print("=" * 80)
response1 = completion(
    model="gemini/gemini-3-flash-preview",
    messages=[
        {"role": "user", "content": "List 3 items with markdown headers like ### Item 1"}
    ],
    max_tokens=500,
    api_key=api_key,
    stop=["##"]
)
print(f"Response: {response1.choices[0].message.content}")
print(f"Tokens: {response1.usage.completion_tokens}")
print(f"Finish reason: {response1.choices[0].finish_reason}")

# Test 2: Without stop sequences
print("\n" + "=" * 80)
print("TEST 2: Without stop sequences")
print("=" * 80)
response2 = completion(
    model="gemini/gemini-3-flash-preview",
    messages=[
        {"role": "user", "content": "List 3 items with markdown headers like ### Item 1"}
    ],
    max_tokens=500,
    api_key=api_key,
)
print(f"Response: {response2.choices[0].message.content}")
print(f"Tokens: {response2.usage.completion_tokens}")
print(f"Finish reason: {response2.choices[0].finish_reason}")
