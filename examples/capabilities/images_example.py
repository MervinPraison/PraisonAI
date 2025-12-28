"""
Images Capability Example

Demonstrates image generation using PraisonAI capabilities.
"""

from praisonai.capabilities import image_generate

# Generate an image with DALL-E 2
print("=== Image Generation (DALL-E 2) ===")
result = image_generate(
    prompt="A simple blue circle on a white background",
    model="dall-e-2",
    size="256x256",
    n=1
)
print(f"Images generated: {len(result)}")
if result:
    print(f"URL: {result[0].url[:80]}...")

# Generate with DALL-E 3 (higher quality)
print("\n=== Image Generation (DALL-E 3) ===")
result = image_generate(
    prompt="A serene mountain landscape at sunset",
    model="dall-e-3",
    size="1024x1024",
    quality="standard"
)
print(f"Images generated: {len(result)}")
if result:
    print(f"Revised prompt: {result[0].revised_prompt[:80]}..." if result[0].revised_prompt else "No revised prompt")
