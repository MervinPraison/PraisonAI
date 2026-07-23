# praisonai: skip=true
"""
Example: Using MuAPI with PraisonAI for image generation.

MuAPI (https://muapi.ai) provides unified access to 400+ generative media
models — Flux, Midjourney, GPT-4o Image, Google Imagen, Seedream, Veo3,
Kling, Wan, and more — through a single API.

This example creates a PraisonAI agent that generates images on demand
using the MuAPI image generation API as a custom tool.

Setup:
    pip install praisonaiagents requests
    export MUAPI_API_KEY=your_key_here
    # Get an API key at https://muapi.ai/dashboard/api-keys
"""

import os
import time

import requests
from praisonaiagents import Agent, Tool


MUAPI_BASE_URL = "https://api.muapi.ai/api/v1"

ALLOWED_MODELS = {
    "flux-schnell", "flux-dev", "flux-kontext-dev", "flux-kontext-pro",
    "midjourney", "gpt4o", "imagen4", "imagen4-fast", "seedream",
    "hidream-fast", "hidream-dev", "reve", "ideogram", "hunyuan",
}


def generate_image(prompt: str, model: str = "flux-schnell") -> str:
    """Generate an image using MuAPI and return the output URL.

    Args:
        prompt: Text description of the image to generate.
        model: MuAPI model ID. Options include flux-schnell, flux-dev,
               midjourney, gpt4o, imagen4, seedream, hidream-fast, reve.

    Returns:
        URL of the generated image.
    """
    if model not in ALLOWED_MODELS:
        raise ValueError(
            f"Unsupported model '{model}'. Choose from: {sorted(ALLOWED_MODELS)}"
        )

    api_key = os.environ.get("MUAPI_API_KEY", "")
    if not api_key:
        raise ValueError("MUAPI_API_KEY environment variable not set")

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    # Submit the generation request
    submit_resp = requests.post(
        f"{MUAPI_BASE_URL}/{model}",
        headers=headers,
        json={"prompt": prompt},
        timeout=30,
    )
    submit_resp.raise_for_status()
    submit_data = submit_resp.json()
    request_id = submit_data.get("request_id")
    if not request_id:
        raise RuntimeError(f"MuAPI did not return a request_id: {submit_data}")

    # Poll until completion
    for _ in range(120):
        time.sleep(3)
        poll_resp = requests.get(
            f"{MUAPI_BASE_URL}/predictions/{request_id}/result",
            headers={"x-api-key": api_key},
            timeout=15,
        )
        poll_resp.raise_for_status()
        data = poll_resp.json()
        status = data.get("status")
        if status == "completed":
            outputs = data.get("outputs") or []
            if not outputs:
                raise RuntimeError(f"Generation completed but returned no outputs: {data}")
            return outputs[0]
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"Image generation {status}: {data.get('error', '')}")

    raise TimeoutError("Image generation timed out after 6 minutes")


if __name__ == "__main__":
    image_tool = Tool(
        name="generate_image",
        description=(
            "Generate an image from a text description using MuAPI's 400+ model library. "
            "Supported models: flux-schnell (fast), flux-dev, midjourney, gpt4o, imagen4, "
            "seedream, hidream-fast, reve. Returns a URL to the generated image."
        ),
        function=generate_image,
    )

    agent = Agent(
        name="Image Generator",
        instructions=(
            "You are a creative image generation assistant. "
            "When asked to create an image, use the generate_image tool. "
            "Pick the best model for the task: flux-schnell for speed, "
            "midjourney for artistic quality, gpt4o for photorealism."
        ),
        tools=[image_tool],
    )

    # Example: generate a product photo
    response = agent.start(
        "Generate a photorealistic product photo of a sleek black coffee mug "
        "on a white marble table with soft morning light. Use the best model for photorealism."
    )
    print(response)

    # Example: generate concept art
    response = agent.start(
        "Create a cyberpunk cityscape at night with neon reflections on wet streets. "
        "Use midjourney for artistic quality."
    )
    print(response)
