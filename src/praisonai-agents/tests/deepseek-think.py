from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Why sky is Blue?"},
    ],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="", flush=True)
    if chunk.choices[0].delta.reasoning_content is not None:
        print(chunk.choices[0].delta.reasoning_content, end="", flush=True)