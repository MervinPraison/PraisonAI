from langtrace_python_sdk import langtrace
from langtrace_python_sdk.utils.with_root_span import with_langtrace_root_span
# Paste this code after your langtrace init function
import os
from openai import OpenAI

langtrace.init(
    api_key=os.getenv('LANGTRACE_API_KEY', os.environ.get('LANGTRACE_API_KEY')),
    api_host="http://localhost:3000/api/trace"
)

@with_langtrace_root_span()
def example():
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "How many states of matter are there?"
            }
        ],
    )
    print(response.choices[0].message.content)

example()