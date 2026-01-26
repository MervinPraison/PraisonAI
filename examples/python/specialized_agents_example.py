"""
Specialized Agents Example

Demonstrates using specialized agent types (AudioAgent, VideoAgent, ImageAgent, OCRAgent)
with the Agents class for multi-agent workflows.

Usage:
    python specialized_agents_example.py
"""

# Example 1: Simple TTS with AudioAgent
def example_tts():
    """Text-to-Speech example using AudioAgent."""
    from praisonaiagents import AudioAgent
    
    agent = AudioAgent(llm="openai/tts-1")
    agent.speech("Hello, welcome to PraisonAI!", output="hello.mp3")
    print("Generated: hello.mp3")

# Example 2: Simple STT with AudioAgent
def example_stt():
    """Speech-to-Text example using AudioAgent."""
    from praisonaiagents import AudioAgent
    
    agent = AudioAgent(llm="openai/whisper-1")
    text = agent.transcribe("hello.mp3")
    print(f"Transcribed: {text}")

# Example 3: Image generation with ImageAgent
def example_image():
    """Image generation example using ImageAgent."""
    from praisonaiagents import ImageAgent
    
    agent = ImageAgent(llm="openai/dall-e-3")
    result = agent.generate("A beautiful sunset over mountains")
    print(f"Generated image: {result}")

# Example 4: Multi-agent pipeline with mixed agent types via YAML
def example_multi_agent_pipeline():
    """
    Multi-agent pipeline example using YAML workflow:
    1. AudioAgent (STT) - Transcribe audio
    2. Agent (Research) - Research the topic
    3. ImageAgent - Generate image
    
    Note: Specialized agents (AudioAgent, VideoAgent, etc.) are best used
    through YAML workflows or directly via their methods (speech, transcribe, etc.)
    """
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
    
    # Define multi-agent pipeline in YAML
    yaml_content = """
name: Multi-Agent Pipeline
process: sequential

agents:
  transcriber:
    agent: AudioAgent
    llm: openai/whisper-1
    role: Transcriber
    goal: Transcribe audio to text
  
  researcher:
    role: Research Specialist
    goal: Research topics and provide summaries
    instructions: You research topics and provide concise summaries.
  
  artist:
    agent: ImageAgent
    llm: openai/dall-e-3
    role: Visual Artist
    goal: Create images based on research

steps:
  - agent: transcriber
    action: transcribe
    input: "{{audio_file}}"
  
  - agent: researcher
    action: "Research the following topic and provide a summary: {{previous_output}}"
  
  - agent: artist
    action: generate
    prompt: "Create an image representing: {{previous_output}}"

variables:
  audio_file: input.mp3
"""
    
    parser = YAMLWorkflowParser()
    workflow = parser.parse_string(yaml_content)
    
    print("Multi-agent pipeline created successfully!")
    print(f"Workflow: {workflow.name}")
    print(f"Agents: {list(parser._agents.keys())}")
    print(f"Agent types: {[a.__class__.__name__ for a in parser._agents.values()]}")
    print(f"Steps: {len(workflow.steps)}")

# Example 5: Using YAML workflow with specialized agents
def example_yaml_workflow():
    """Parse YAML workflow with specialized agent types."""
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
    
    yaml_content = """
name: Media Pipeline
process: sequential

agents:
  transcriber:
    agent: AudioAgent
    llm: openai/whisper-1
    role: Transcriber
    goal: Transcribe audio
  
  researcher:
    role: Researcher
    goal: Research topics
  
  artist:
    agent: ImageAgent
    llm: openai/dall-e-3
    role: Artist
    goal: Create images

steps:
  - agent: transcriber
    action: transcribe
  - agent: researcher
    action: "Research: {{previous_output}}"
  - agent: artist
    action: generate
"""
    
    parser = YAMLWorkflowParser()
    workflow = parser.parse_string(yaml_content)
    
    print(f"Workflow: {workflow.name}")
    print(f"Agents: {list(parser._agents.keys())}")
    print(f"Agent types: {[a.__class__.__name__ for a in parser._agents.values()]}")


if __name__ == "__main__":
    print("=" * 60)
    print("Specialized Agents Examples")
    print("=" * 60)
    
    # Run the YAML workflow example (doesn't require API keys)
    print("\n--- Example: YAML Workflow with Specialized Agents ---")
    example_yaml_workflow()
    
    print("\n--- Example: Multi-Agent Pipeline ---")
    example_multi_agent_pipeline()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)
