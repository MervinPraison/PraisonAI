"""
Tests for specialized agent support in YAML workflow parser.

Tests the ability to use `agent:` field to specify specialized agent types
like AudioAgent, VideoAgent, ImageAgent, OCRAgent in YAML workflows.
"""

import pytest


class TestSpecializedAgentParsing:
    """Test parsing of specialized agent types from YAML."""
    
    def test_parse_audio_agent_type(self):
        """Test that agent: AudioAgent creates an AudioAgent instance."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: TTS Workflow
agents:
  speaker:
    agent: AudioAgent
    llm: openai/tts-1
    role: Text-to-Speech Agent
    goal: Convert text to speech
steps:
  - agent: speaker
    action: speech
    text: "Hello world"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Verify the agent is an AudioAgent
        assert len(parser._agents) == 1
        agent = parser._agents['speaker']
        assert agent.__class__.__name__ == 'AudioAgent'
    
    def test_parse_video_agent_type(self):
        """Test that agent: VideoAgent creates a VideoAgent instance."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Video Workflow
agents:
  creator:
    agent: VideoAgent
    llm: openai/sora-2
    role: Video Creator
    goal: Generate videos
steps:
  - agent: creator
    action: generate
    prompt: "A sunset over mountains"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['creator']
        assert agent.__class__.__name__ == 'VideoAgent'
    
    def test_parse_image_agent_type(self):
        """Test that agent: ImageAgent creates an ImageAgent instance."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Image Workflow
agents:
  artist:
    agent: ImageAgent
    llm: openai/dall-e-3
    role: Image Creator
    goal: Generate images
steps:
  - agent: artist
    action: generate
    prompt: "A beautiful landscape"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['artist']
        assert agent.__class__.__name__ == 'ImageAgent'
    
    def test_parse_ocr_agent_type(self):
        """Test that agent: OCRAgent creates an OCRAgent instance."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: OCR Workflow
agents:
  reader:
    agent: OCRAgent
    role: Document Reader
    goal: Extract text from documents
steps:
  - agent: reader
    action: extract
    source: "document.pdf"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['reader']
        assert agent.__class__.__name__ == 'OCRAgent'
    
    def test_parse_default_agent_type(self):
        """Test that no agent: field creates a default Agent instance."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Default Workflow
agents:
  assistant:
    role: AI Assistant
    goal: Help users
steps:
  - agent: assistant
    action: "Help me with something"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['assistant']
        assert agent.__class__.__name__ == 'Agent'
    
    def test_parse_mixed_agent_types(self):
        """Test parsing workflow with multiple specialized agent types."""
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
    tools:
      - tavily_search
  artist:
    agent: ImageAgent
    llm: openai/dall-e-3
    role: Artist
    goal: Create images
steps:
  - agent: transcriber
    action: transcribe
  - agent: researcher
    action: "Research {{previous_output}}"
  - agent: artist
    action: generate
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Verify each agent type
        assert parser._agents['transcriber'].__class__.__name__ == 'AudioAgent'
        assert parser._agents['researcher'].__class__.__name__ == 'Agent'
        assert parser._agents['artist'].__class__.__name__ == 'ImageAgent'
    
    def test_agent_field_case_insensitive(self):
        """Test that agent type field is case-insensitive."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Case Test
agents:
  speaker:
    agent: audioagent
    llm: openai/tts-1
    role: Speaker
    goal: Speak
steps:
  - agent: speaker
    action: speech
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['speaker']
        assert agent.__class__.__name__ == 'AudioAgent'


class TestSpecializedAgentActions:
    """Test action mapping for specialized agents."""
    
    def test_audio_agent_speech_action(self):
        """Test that action: speech maps to AudioAgent.speech()."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: TTS Test
agents:
  speaker:
    agent: AudioAgent
    llm: openai/tts-1
    role: Speaker
    goal: Speak
steps:
  - agent: speaker
    action: speech
    text: "Hello world"
    output: "hello.mp3"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['speaker']
        # Verify action is stored
        assert hasattr(agent, '_yaml_action')
        assert agent._yaml_action == 'speech'
    
    def test_audio_agent_transcribe_action(self):
        """Test that action: transcribe maps to AudioAgent.transcribe()."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: STT Test
agents:
  transcriber:
    agent: AudioAgent
    llm: openai/whisper-1
    role: Transcriber
    goal: Transcribe
steps:
  - agent: transcriber
    action: transcribe
    input: "audio.mp3"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['transcriber']
        assert hasattr(agent, '_yaml_action')
        assert agent._yaml_action == 'transcribe'
    
    def test_video_agent_generate_action(self):
        """Test that action: generate maps to VideoAgent.generate()."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Video Test
agents:
  creator:
    agent: VideoAgent
    llm: openai/sora-2
    role: Creator
    goal: Create videos
steps:
  - agent: creator
    action: generate
    prompt: "A cat playing"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['creator']
        assert hasattr(agent, '_yaml_action')
        assert agent._yaml_action == 'generate'
    
    def test_image_agent_generate_action(self):
        """Test that action: generate maps to ImageAgent.generate()."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Image Test
agents:
  artist:
    agent: ImageAgent
    llm: openai/dall-e-3
    role: Artist
    goal: Create images
steps:
  - agent: artist
    action: generate
    prompt: "A mountain"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['artist']
        assert hasattr(agent, '_yaml_action')
        assert agent._yaml_action == 'generate'
    
    def test_ocr_agent_extract_action(self):
        """Test that action: extract maps to OCRAgent.extract()."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: OCR Test
agents:
  reader:
    agent: OCRAgent
    role: Reader
    goal: Read documents
steps:
  - agent: reader
    action: extract
    source: "document.pdf"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        agent = parser._agents['reader']
        assert hasattr(agent, '_yaml_action')
        assert agent._yaml_action == 'extract'


class TestMultiAgentPipeline:
    """Test multi-agent pipelines with specialized agents."""
    
    def test_five_agent_media_pipeline(self):
        """Test the 5-agent media pipeline: STT → Research → Image → Video → TTS."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Media Pipeline
description: Complete media pipeline from audio to video
process: sequential

agents:
  transcriber:
    agent: AudioAgent
    llm: openai/whisper-1
    role: Audio Transcriber
    goal: Convert audio to text
  
  researcher:
    role: Research Specialist
    goal: Research the topic
    tools:
      - tavily_search
  
  image_creator:
    agent: ImageAgent
    llm: openai/dall-e-3
    role: Visual Artist
    goal: Create images
  
  video_creator:
    agent: VideoAgent
    llm: openai/sora-2
    role: Video Producer
    goal: Create videos
  
  narrator:
    agent: AudioAgent
    llm: openai/tts-1-hd
    role: Voice Narrator
    goal: Create voiceovers

steps:
  - agent: transcriber
    action: transcribe
    input: "{{audio_file}}"
  
  - agent: researcher
    action: "Research based on: {{previous_output}}"
  
  - agent: image_creator
    action: generate
    prompt: "{{previous_output}}"
  
  - agent: video_creator
    action: generate
    prompt: "{{previous_output}}"
  
  - agent: narrator
    action: speech
    text: "{{previous_output}}"
    output: "voiceover.mp3"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Verify all agents are created with correct types
        assert parser._agents['transcriber'].__class__.__name__ == 'AudioAgent'
        assert parser._agents['researcher'].__class__.__name__ == 'Agent'
        assert parser._agents['image_creator'].__class__.__name__ == 'ImageAgent'
        assert parser._agents['video_creator'].__class__.__name__ == 'VideoAgent'
        assert parser._agents['narrator'].__class__.__name__ == 'AudioAgent'
        
        # Verify workflow has 5 steps
        assert len(workflow.steps) == 5
    
    def test_context_passing_between_specialized_agents(self):
        """Test that {{previous_output}} works between specialized agents."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Context Test
agents:
  transcriber:
    agent: AudioAgent
    llm: openai/whisper-1
    role: Transcriber
    goal: Transcribe
  artist:
    agent: ImageAgent
    llm: openai/dall-e-3
    role: Artist
    goal: Create images
steps:
  - agent: transcriber
    action: transcribe
    input: "audio.mp3"
  - agent: artist
    action: "Create an image based on: {{previous_output}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Verify workflow is created successfully
        assert len(workflow.steps) == 2
        
        # Verify the second step has the action with template
        artist = parser._agents['artist']
        assert '{{previous_output}}' in artist._yaml_action
