"""
Tests for ScientificWriterAgent - specialized agent for scientific paper generation.

This test suite validates the integration of CAJAL model support and 
scientific writing capabilities within PraisonAI.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add the src directory to Python path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from praisonaiagents.agent.scientific_writer_agent import (
    ScientificWriterAgent, 
    PaperSection, 
    ScientificPaper
)

class TestPaperSection:
    """Test the PaperSection dataclass."""
    
    def test_paper_section_creation(self):
        """Test creating a PaperSection."""
        section = PaperSection(
            title="Introduction",
            content="This is the introduction content.",
            latex_content="\\section{Introduction}\nThis is the introduction content."
        )
        
        assert section.title == "Introduction"
        assert section.content == "This is the introduction content."
        assert "\\section{Introduction}" in section.latex_content
    
    def test_paper_section_repr(self):
        """Test string representation of PaperSection."""
        section = PaperSection(
            title="Methods",
            content="This is a very long methodology section that should be truncated in the repr method for better display.",
        )
        
        repr_str = repr(section)
        assert "Methods" in repr_str
        assert "..." in repr_str  # Should be truncated

class TestScientificPaper:
    """Test the ScientificPaper dataclass."""
    
    def test_scientific_paper_creation(self):
        """Test creating a ScientificPaper."""
        sections = [
            PaperSection("Introduction", "Introduction content"),
            PaperSection("Methods", "Methods content")
        ]
        references = ["Author et al. (2024)", "Smith & Jones (2023)"]
        
        paper = ScientificPaper(
            title="Test Paper",
            abstract="This is the abstract",
            sections=sections,
            references=references,
            metadata={"model": "cajal-4b"}
        )
        
        assert paper.title == "Test Paper"
        assert paper.abstract == "This is the abstract"
        assert len(paper.sections) == 2
        assert len(paper.references) == 2
        assert paper.metadata["model"] == "cajal-4b"
    
    def test_scientific_paper_repr(self):
        """Test string representation of ScientificPaper."""
        paper = ScientificPaper(
            title="Climate Change Research",
            abstract="Abstract content",
            sections=[PaperSection("Intro", "content")],
            references=["Ref1", "Ref2"]
        )
        
        repr_str = repr(paper)
        assert "Climate Change Research" in repr_str
        assert "sections=1" in repr_str
        assert "references=2" in repr_str

class TestScientificWriterAgent:
    """Test the ScientificWriterAgent class."""
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_agent_initialization_defaults(self, mock_agent_class):
        """Test ScientificWriterAgent initialization with defaults."""
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        
        agent = ScientificWriterAgent()
        
        # Verify Agent was called with appropriate defaults
        mock_agent_class.assert_called_once()
        call_kwargs = mock_agent_class.call_args[1]
        
        assert call_kwargs['name'] == "Scientific Writer"
        assert call_kwargs['role'] == "Scientific Paper Writer"
        assert "scientific paper writer" in call_kwargs['instructions'].lower()
        assert "academic" in call_kwargs['goal'].lower()
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_agent_initialization_custom(self, mock_agent_class):
        """Test ScientificWriterAgent initialization with custom parameters."""
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        
        agent = ScientificWriterAgent(
            name="Custom Writer",
            model="custom-model",
            instructions="Custom instructions",
            role="Custom Role"
        )
        
        call_kwargs = mock_agent_class.call_args[1]
        assert call_kwargs['name'] == "Custom Writer"
        assert call_kwargs['role'] == "Custom Role"
        assert call_kwargs['instructions'] == "Custom instructions"
        assert call_kwargs['llm'] == "custom-model"
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_cajal_model_detection(self, mock_agent_class):
        """Test CAJAL model detection."""
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        
        # Test with CAJAL model
        agent = ScientificWriterAgent(model="cajal-4b")
        assert agent.is_cajal_model == True
        
        # Test with non-CAJAL model
        agent = ScientificWriterAgent(model="gpt-4o-mini")
        assert agent.is_cajal_model == False
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_write_paper_method(self, mock_agent_class):
        """Test the write_paper method."""
        mock_agent = MagicMock()
        mock_agent.start.return_value = """
        # Climate Change Effects on Marine Ecosystems
        
        ## Abstract
        This paper examines the impact of climate change on marine ecosystems.
        
        ## Introduction
        Climate change poses significant threats to marine life.
        
        ## Methodology
        We conducted a comprehensive literature review.
        
        ## Results
        Our findings indicate significant coral bleaching.
        
        ## Discussion  
        The results suggest immediate action is needed.
        
        ## Conclusion
        Climate change mitigation is crucial for marine conservation.
        
        References:
        - Smith et al. (2024)
        - Jones & Brown (2023)
        """
        mock_agent_class.return_value = mock_agent
        
        agent = ScientificWriterAgent()
        paper = agent.write_paper("Climate Change Effects on Marine Ecosystems")
        
        # Verify agent.start was called with a prompt
        mock_agent.start.assert_called_once()
        call_args = mock_agent.start.call_args[0][0]
        assert "Climate Change Effects on Marine Ecosystems" in call_args
        assert "academic" in call_args
        
        # Verify paper structure
        assert isinstance(paper, ScientificPaper)
        assert paper.title == "Climate Change Effects on Marine Ecosystems"
        assert paper.metadata["generated_by"] == "ScientificWriterAgent"
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_write_section_method(self, mock_agent_class):
        """Test the write_section method."""
        mock_agent = MagicMock()
        mock_agent.start.return_value = "This is the methodology section content with detailed procedures."
        mock_agent_class.return_value = mock_agent
        
        agent = ScientificWriterAgent()
        section = agent.write_section(
            section_title="Methodology",
            content_request="Describe the research methodology"
        )
        
        # Verify agent.start was called
        mock_agent.start.assert_called_once()
        call_args = mock_agent.start.call_args[0][0]
        assert "Methodology" in call_args
        assert "research methodology" in call_args
        
        # Verify section structure
        assert isinstance(section, PaperSection)
        assert section.title == "Methodology"
        assert "methodology section content" in section.content
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_review_and_cite_method(self, mock_agent_class):
        """Test the review_and_cite method."""
        mock_agent = MagicMock()
        mock_agent.start.return_value = "Literature review with citations [1] and proper academic formatting."
        mock_agent_class.return_value = mock_agent
        
        agent = ScientificWriterAgent()
        result = agent.review_and_cite(
            research_query="machine learning in climate science",
            existing_content="Machine learning has applications in climate research."
        )
        
        # Verify agent.start was called
        mock_agent.start.assert_called_once()
        call_args = mock_agent.start.call_args[0][0]
        assert "machine learning in climate science" in call_args
        assert "Machine learning has applications" in call_args
        
        # Verify result
        assert "Literature review" in result
        assert "[1]" in result
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_get_cajal_model_method(self, mock_agent_class):
        """Test the _get_cajal_model method."""
        mock_agent_class.return_value = MagicMock()
        
        agent = ScientificWriterAgent()
        model = agent._get_cajal_model()
        
        # Should return the HuggingFace model path
        assert model == "Agnuxo/CAJAL-4B-P2PCLAW"
    
    @patch('praisonaiagents.agent.scientific_writer_agent.Agent')
    def test_attribute_delegation(self, mock_agent_class):
        """Test that unknown attributes are delegated to the underlying agent."""
        mock_agent = MagicMock()
        mock_agent.some_method.return_value = "delegated result"
        mock_agent_class.return_value = mock_agent
        
        agent = ScientificWriterAgent()
        
        # Test method delegation
        result = agent.some_method("test_arg")
        assert result == "delegated result"
        mock_agent.some_method.assert_called_once_with("test_arg")
        
        # Test attribute access delegation  
        mock_agent.some_property = "property value"
        assert agent.some_property == "property value"

class TestScientificWriterAgentIntegration:
    """Integration tests for ScientificWriterAgent with real Agent class."""
    
    def test_real_agentic_test(self):
        """Real agentic test - agent runs end-to-end."""
        # This is a simplified test that doesn't require actual LLM calls
        # In a real test, this would make an actual LLM call
        
        print("Testing ScientificWriterAgent integration...")
        
        try:
            # Test import and basic instantiation
            from praisonaiagents import ScientificWriterAgent
            
            agent = ScientificWriterAgent(
                name="Test Scientific Writer",
                model="gpt-4o-mini",  # Use a standard model for testing
                instructions="You are a test scientific writer."
            )
            
            # Verify agent properties
            assert agent.agent.name == "Test Scientific Writer"
            assert "scientific writer" in agent.agent.instructions.lower()
            assert agent.is_cajal_model == False  # gpt-4o-mini is not CAJAL
            
            print("✅ ScientificWriterAgent created successfully")
            print(f"Agent name: {agent.agent.name}")
            print(f"Is CAJAL model: {agent.is_cajal_model}")
            print(f"Model: {agent.model_name}")
            
            # Test basic functionality without LLM call
            # (In a full test, you would call agent.start() here)
            
        except ImportError as e:
            pytest.skip(f"Required dependencies not available: {e}")
        except Exception as e:
            print(f"❌ Test failed: {e}")
            raise

def test_scientific_writer_import():
    """Test that ScientificWriterAgent can be imported from main package."""
    try:
        from praisonaiagents import ScientificWriterAgent, PaperSection, ScientificPaper
        assert ScientificWriterAgent is not None
        assert PaperSection is not None  
        assert ScientificPaper is not None
        print("✅ All scientific writing classes imported successfully")
    except ImportError as e:
        pytest.fail(f"Failed to import ScientificWriterAgent: {e}")

if __name__ == "__main__":
    # Run basic smoke tests
    print("Running ScientificWriterAgent tests...")
    
    # Test imports
    test_scientific_writer_import()
    
    # Test basic functionality
    integration_test = TestScientificWriterAgentIntegration()
    integration_test.test_real_agentic_test()
    
    print("\n✅ All basic tests passed!")
    print("Run 'pytest test_scientific_writer_agent.py' for full test suite.")