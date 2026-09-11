"""Basic example of using Eden AI with PraisonAI.

Eden AI is an AI gateway: a single OpenAI-compatible endpoint fronts models from
many vendors. Select one with ``edenai/<vendor>/<model>`` -- the ``<vendor>/<model>``
part is Eden AI's own model identifier and is forwarded unchanged, so any model
Eden AI serves works without a PraisonAI update.

Setup:
    export EDENAI_API_KEY=your_api_key

Optionally point at a different Eden AI endpoint (defaults to
https://api.edenai.run/v3):

    export EDENAI_BASE_URL=https://api.edenai.run/v3

EDENAI_API_KEY is required for an Eden AI model. PraisonAI will not fall back to
OPENAI_API_KEY for these routes, so your OpenAI credential is never sent to
Eden AI.
"""

import os

from praisonaiagents import Agent

if not os.getenv("EDENAI_API_KEY"):
    raise RuntimeError(
        "EDENAI_API_KEY is not set. Set it before running this example: "
        "export EDENAI_API_KEY=your_api_key"
    )

agent = Agent(
    instructions="You are a helpful assistant",
    llm="edenai/openai/gpt-4.1-mini",
)

response = agent.start("Hello! Share one practical AI automation idea.")
print(response)


# Switching vendors is a change of model string -- same key, same endpoint.
for model in [
    "edenai/anthropic/claude-sonnet-4-5",
    "edenai/google/gemini-2.5-flash",
]:
    vendor_agent = Agent(
        instructions="You are a concise technical writer",
        llm=model,
    )
    print(f"\n--- {model} ---")
    print(vendor_agent.start("Explain quantum entanglement in two sentences."))
