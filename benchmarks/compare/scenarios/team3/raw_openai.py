# Baseline: three chained calls with the raw SDK. https://platform.openai.com/docs/api-reference/chat
import os

from openai import OpenAI

URL = os.environ["BENCH_STUB_URL"] + "/v1"  # bench:config
STEPS = ["Research the topic.", "Write a draft from the research.", "Edit the draft."]


def build():
    return OpenAI(base_url=URL)


def run(client):
    text = "AI agents"
    for instructions in STEPS:
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": text}]
        text = client.chat.completions.create(model="gpt-4o-mini", messages=messages).choices[0].message.content
    return text
