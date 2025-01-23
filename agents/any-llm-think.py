from litellm import completion
messages = [{"role": "user", "content": "Why is the sky blue?"}]
response = completion(model="deepseek/deepseek-reasoner", messages=messages, stream=False)
print(response)

# for chunk in response:
#     if chunk.choices[0].delta.content is not None:
#         print(chunk.choices[0].delta.content, end="", flush=True)
#     if chunk.choices[0].delta.reasoning_content is not None:
#         print(chunk.choices[0].delta.reasoning_content, end="", flush=True)