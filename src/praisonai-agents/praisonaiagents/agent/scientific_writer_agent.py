"""
Scientific Writer Agent Module

This module provides the ScientificWriterAgent class for generating scientific papers
using CAJAL (Specialized Scientific Paper Agent) from P2PCLAW.

CAJAL is a 2GB local model specialized for scientific paper generation, producing
LaTeX-formatted academic output. It's part of the P2PCLAW decentralized research network.

Features:
- Local 2GB model for privacy and offline operation
- LaTeX-formatted academic output
- Specialized for scientific paper generation
- Integration with PraisonAI multi-agent workflows

Example:
    from praisonaiagents import ScientificWriterAgent
    
    # Basic usage
    agent = ScientificWriterAgent(
        name="Research Paper Writer",
        model="cajal-4b",
        instructions="You are a specialized scientific paper writer"
    )
    
    paper = agent.write_paper("Write a paper on climate change effects on coral reefs")
    print(paper.latex_content)
    
    # Multi-agent workflow
    from praisonaiagents import Agent, AgentTeam, Task
    
    literature_reviewer = Agent(
        name="Literature Reviewer", 
        model="cajal-4b",
        instructions="Review and cite relevant literature"
    )
    
    methodology_designer = Agent(
        name="Methodology Designer",
        instructions="Design research methodology"
    )
    
    scientific_writer = ScientificWriterAgent(
        name="Scientific Writer",
        model="cajal-4b"
    )
    
    team = AgentTeam(
        agents=[literature_reviewer, methodology_designer, scientific_writer],
        tasks=[
            Task("review_literature", "Review literature on the topic", literature_reviewer),
            Task("design_methodology", "Design research methodology", methodology_designer),
            Task("write_paper", "Write the scientific paper", scientific_writer)
        ]
    )
"""

import os
import re
import logging
from praisonaiagents._logging import get_logger
from typing import List, Optional, Any, Dict, Union
from dataclasses import dataclass, field
from .agent import Agent

logger = get_logger(__name__)

@dataclass
class PaperSection:
    """Represents a section of a scientific paper."""
    title: str
    content: str
    latex_content: str = ""
    
    def __repr__(self):
        content_preview = self.content[:100] + "..." if len(self.content) > 100 else self.content
        return f"PaperSection(title='{self.title}', content='{content_preview}')"

@dataclass
class ScientificPaper:
    """Represents a complete scientific paper with LaTeX formatting."""
    title: str
    abstract: str
    sections: List[PaperSection] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    latex_content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self):
        return f"ScientificPaper(title='{self.title}', sections={len(self.sections)}, references={len(self.references)})"

class ScientificWriterAgent:
    """
    Specialized agent for scientific paper generation using CAJAL model.
    
    This agent integrates the CAJAL model from P2PCLAW for generating academic papers
    in LaTeX format. It follows the protocol-driven design of PraisonAI while providing
    specialized functionality for scientific writing.
    
    The agent can work standalone or as part of a multi-agent workflow with
    literature reviewers, methodology designers, and other research agents.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        model: Optional[str] = None,
        instructions: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize a ScientificWriterAgent.
        
        Args:
            name: Agent name (defaults to "Scientific Writer")
            model: Model to use (defaults to "cajal-4b" if available)
            instructions: Custom instructions for the agent
            role: Agent role (defaults to "Scientific Paper Writer")
            goal: Agent goal (defaults to scientific writing goal)
            backstory: Agent backstory (defaults to scientific writing backstory)
            **kwargs: Additional arguments passed to base Agent
        """
        # Set defaults for scientific writing
        name = name or "Scientific Writer"
        role = role or "Scientific Paper Writer"
        goal = goal or "Generate high-quality scientific papers with proper academic formatting and citations"
        backstory = backstory or (
            "You are a specialized scientific paper writer trained on academic literature. "
            "You excel at creating well-structured, properly cited research papers in LaTeX format. "
            "You understand academic conventions, citation styles, and the importance of rigorous methodology."
        )
        
        # Default instructions for scientific writing
        if not instructions:
            instructions = (
                "You are a specialized scientific paper writer. Your role is to create high-quality "
                "academic papers with proper structure, citations, and LaTeX formatting. "
                "Always follow academic conventions and ensure rigorous methodology. "
                "Focus on clarity, precision, and scholarly communication."
            )
        
        # Set default model to CAJAL if not specified
        if not model:
            # Check if CAJAL is available, fallback to default model
            model = self._get_cajal_model()
        
        # Initialize the base Agent with scientific writing configuration
        self.agent = Agent(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            llm=model,
            **kwargs
        )
        
        # Store CAJAL-specific configuration
        self.is_cajal_model = "cajal" in (model or "").lower()
        self.model_name = model
        
        logger.info(f"Initialized ScientificWriterAgent '{name}' with model '{model}'")
    
    def _get_cajal_model(self) -> str:
        """
        Return the default CAJAL model identifier.

        Returns:
            Model name to use for scientific writing
        """
        # Return the HuggingFace model path for CAJAL
        return "Agnuxo/CAJAL-4B-P2PCLAW"
    
    def write_paper(
        self, 
        topic: str,
        sections: Optional[List[str]] = None,
        style: str = "academic",
        citation_style: str = "APA"
    ) -> ScientificPaper:
        """
        Generate a complete scientific paper on the given topic.
        
        Args:
            topic: The research topic or question
            sections: List of section titles to include (defaults to standard academic sections)
            style: Writing style ("academic", "review", "research")
            citation_style: Citation style to use ("APA", "IEEE", "Nature")
            
        Returns:
            ScientificPaper object with generated content
        """
        if not sections:
            sections = ["Introduction", "Literature Review", "Methodology", "Results", "Discussion", "Conclusion"]
        
        # Construct the prompt for paper generation
        prompt = self._build_paper_prompt(topic, sections, style, citation_style)
        
        # Generate the paper using the agent
        response = self.agent.start(prompt)
        
        # Parse the response into a structured ScientificPaper object
        paper = self._parse_paper_response(response, topic, sections)
        
        return paper
    
    def write_section(
        self,
        section_title: str,
        content_request: str,
        context: Optional[str] = None
    ) -> PaperSection:
        """
        Generate a specific section of a scientific paper.
        
        Args:
            section_title: Title of the section to generate
            content_request: Specific request for the section content
            context: Additional context or previous sections
            
        Returns:
            PaperSection object with generated content
        """
        prompt = f"""
        Write a {section_title} section for a scientific paper.
        
        Content request: {content_request}
        
        {f"Context from previous sections: {context}" if context else ""}
        
        Please provide:
        1. Well-structured content appropriate for the {section_title} section
        2. Proper academic language and formatting
        3. LaTeX formatting where appropriate
        4. Citations in proper academic format
        
        Format the output clearly with section headings and proper academic style.
        """
        
        response = self.agent.start(prompt)
        
        # Create a PaperSection object
        section = PaperSection(
            title=section_title,
            content=response,
            latex_content=self._extract_latex(response)
        )
        
        return section
    
    def review_and_cite(
        self,
        research_query: str,
        existing_content: Optional[str] = None
    ) -> str:
        """
        Review literature and add citations to existing content.
        
        Args:
            research_query: The research query for literature review
            existing_content: Existing content to add citations to
            
        Returns:
            Content with added literature review and citations
        """
        if existing_content:
            prompt = f"""
            Please review the following content and add appropriate citations and literature references:
            
            {existing_content}
            
            Research query: {research_query}
            
            Please:
            1. Add relevant citations where appropriate
            2. Include a literature review section if not present
            3. Ensure all claims are properly supported with references
            4. Use proper academic citation format
            """
        else:
            prompt = f"""
            Conduct a literature review on: {research_query}
            
            Please provide:
            1. Overview of current research in the field
            2. Key findings and methodologies
            3. Gaps in the literature
            4. Proper citations and references
            5. LaTeX formatting for academic publication
            """
        
        return self.agent.start(prompt)
    
    def _build_paper_prompt(
        self, 
        topic: str, 
        sections: List[str], 
        style: str, 
        citation_style: str
    ) -> str:
        """Build the prompt for full paper generation."""
        sections_str = "\n".join([f"- {section}" for section in sections])
        
        return f"""
        Write a comprehensive scientific paper on the following topic: {topic}
        
        Required sections:
        {sections_str}
        
        Requirements:
        - Style: {style}
        - Citation style: {citation_style}
        - Use proper LaTeX formatting for academic publication
        - Include appropriate citations and references
        - Maintain rigorous academic standards
        - Structure the paper with clear headings and logical flow
        
        Please provide a complete, well-structured academic paper suitable for publication.
        """
    
    def _parse_paper_response(
        self, 
        response: str, 
        topic: str, 
        sections: List[str]
    ) -> ScientificPaper:
        """Parse the agent response into a structured ScientificPaper object."""
        # Extract title (basic implementation)
        title = topic  # Could be improved with NLP parsing
        
        # Extract abstract (basic implementation)
        abstract = self._extract_section(response, "abstract") or "Abstract not found"
        
        # Extract sections
        paper_sections = []
        for section_name in sections:
            section_content = self._extract_section(response, section_name.lower())
            if section_content:
                paper_sections.append(PaperSection(
                    title=section_name,
                    content=section_content,
                    latex_content=self._extract_latex(section_content)
                ))
        
        # Extract references
        references = self._extract_references(response)
        
        return ScientificPaper(
            title=title,
            abstract=abstract,
            sections=paper_sections,
            references=references,
            latex_content=response,  # Full response as LaTeX
            metadata={
                "model": self.model_name,
                "generated_by": "ScientificWriterAgent",
                "is_cajal": self.is_cajal_model
            }
        )
    
    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """Extract a specific section from the generated text."""
        pattern = rf"##?\s+{re.escape(section_name)}[^\n]*\n(.*?)(?=\n\s*##?\s|\Z)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else None
    
    def _extract_latex(self, text: str) -> str:
        """Extract LaTeX formatting from text."""
        # Basic implementation - return text as-is assuming it contains LaTeX
        return text
    
    def _extract_references(self, text: str) -> List[str]:
        """Extract references from the generated text."""
        ref_pattern = r"\\cite\{[^}]+\}|\[[0-9]+\]"
        references = re.findall(ref_pattern, text)
        return references
    
    # Delegate other methods to the underlying agent
    def __getattr__(self, name):
        """Delegate unknown attributes to the underlying agent."""
        return getattr(self.agent, name)