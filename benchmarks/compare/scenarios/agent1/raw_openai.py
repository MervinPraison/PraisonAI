# Baseline for S2 only (there is no agent object to instantiate).
import os

from openai import OpenAI

URL = os.environ["BENCH_STUB_URL"] + "/v1"


def build(tools):
    return OpenAI(base_url=URL)


def ask(client, prompt):
    messages = [{"role": "user", "content": prompt}]
    return client.chat.completions.create(model="gpt-4o-mini", messages=messages).choices[0].message.content
