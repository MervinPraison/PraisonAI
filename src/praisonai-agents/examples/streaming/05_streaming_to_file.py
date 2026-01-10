"""
Example 5: Streaming to File

Stream LLM output directly to a file as it's generated.
Useful for logging, saving responses, or processing large outputs.

When to use: When you need to save streaming output to disk.
"""
from praisonaiagents import Agent
import tempfile
import os

agent = Agent(
    name="Writer",
    instructions="You write detailed content",
    output="stream"
)

# Create a temp file
output_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)

print(f"Streaming to file: {output_file.name}")
print("Progress: ", end="", flush=True)

char_count = 0
for chunk in agent.start("Write 3 tips for better code"):
    output_file.write(chunk)
    char_count += len(chunk)
    # Show progress dots
    if char_count % 50 == 0:
        print(".", end="", flush=True)

output_file.close()
print(f" Done! ({char_count} chars)")

# Read and display the file
print("\nFile contents:")
print("-" * 40)
with open(output_file.name, 'r') as f:
    print(f.read())

# Cleanup
os.unlink(output_file.name)
