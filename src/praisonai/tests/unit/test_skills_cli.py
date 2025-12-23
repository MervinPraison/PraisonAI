"""
Unit tests for Skills CLI feature.

Tests for:
- Skills create command with all arguments
- AI-generated SKILL.md content
- Template fallback when no API key
- scripts/skill.py auto-generation
- Anthropic Skills API integration
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestSkillsCreateCommand:
    """Tests for skills create command."""
    
    def test_create_skill_basic(self):
        """Test basic skill creation with name and description."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = handler.create_skill(
                name="test-skill",
                description="A test skill",
                output_dir=tmpdir
            )
            
            assert Path(skill_path).exists()
            assert (Path(skill_path) / "SKILL.md").exists()
            assert (Path(skill_path) / "scripts").is_dir()
            assert (Path(skill_path) / "references").is_dir()
            assert (Path(skill_path) / "assets").is_dir()
    
    def test_create_skill_with_author(self):
        """Test skill creation with author metadata."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = handler.create_skill(
                name="test-skill",
                description="A test skill",
                output_dir=tmpdir,
                author="test-author"
            )
            
            skill_md = (Path(skill_path) / "SKILL.md").read_text()
            assert "author: test-author" in skill_md
    
    def test_create_skill_with_license(self):
        """Test skill creation with license."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = handler.create_skill(
                name="test-skill",
                description="A test skill",
                output_dir=tmpdir,
                license="MIT"
            )
            
            skill_md = (Path(skill_path) / "SKILL.md").read_text()
            assert "license: MIT" in skill_md
    
    def test_create_skill_with_compatibility(self):
        """Test skill creation with compatibility info."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = handler.create_skill(
                name="test-skill",
                description="A test skill",
                output_dir=tmpdir,
                compatibility="Works with Python 3.8+"
            )
            
            skill_md = (Path(skill_path) / "SKILL.md").read_text()
            assert "compatibility: Works with Python 3.8+" in skill_md
    
    def test_create_skill_template_mode(self):
        """Test skill creation in template-only mode (no AI)."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = handler.create_skill(
                name="test-skill",
                description="A test skill",
                output_dir=tmpdir,
                template=True  # Force template mode
            )
            
            skill_md = (Path(skill_path) / "SKILL.md").read_text()
            # Template should have placeholder content
            assert "# Test Skill" in skill_md or "# test-skill" in skill_md.lower()


class TestSkillsAIGeneration:
    """Tests for AI-generated skill content."""
    
    def test_ai_generation_with_api_key(self):
        """Test AI generation when API key is available."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        # Mock the LLM call
        with patch.object(handler, '_generate_skill_content_with_ai') as mock_ai:
            mock_ai.return_value = {
                "skill_md": "# AI Generated\n\nAI content here",
                "skill_py": "def process():\n    pass"
            }
            
            with tempfile.TemporaryDirectory() as tmpdir:
                # Set API key
                with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                    skill_path = handler.create_skill(
                        name="ai-skill",
                        description="An AI-generated skill",
                        output_dir=tmpdir,
                        use_ai=True
                    )
                    
                    # Should have called AI generation
                    if hasattr(handler, '_generate_skill_content_with_ai'):
                        mock_ai.assert_called_once()
    
    def test_fallback_to_template_without_api_key(self):
        """Test fallback to template when no API key."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Remove API keys
            env_without_keys = {k: v for k, v in os.environ.items() 
                               if 'API_KEY' not in k.upper()}
            
            with patch.dict(os.environ, env_without_keys, clear=True):
                skill_path = handler.create_skill(
                    name="fallback-skill",
                    description="A fallback skill",
                    output_dir=tmpdir,
                    use_ai=True  # Request AI but no key available
                )
                
                # Should still create skill with template
                assert Path(skill_path).exists()
                assert (Path(skill_path) / "SKILL.md").exists()


class TestSkillsScriptGeneration:
    """Tests for scripts/skill.py auto-generation."""
    
    def test_generate_skill_script(self):
        """Test that scripts/skill.py is generated when requested."""
        from praisonai.cli.features.skills import SkillsHandler
        
        handler = SkillsHandler(verbose=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = handler.create_skill(
                name="script-skill",
                description="A skill with script",
                output_dir=tmpdir,
                generate_script=True
            )
            
            script_path = Path(skill_path) / "scripts" / "skill.py"
            assert script_path.exists()
            
            script_content = script_path.read_text()
            assert "def " in script_content  # Has at least one function


class TestSkillsCLIArguments:
    """Tests for CLI argument parsing."""
    
    def test_output_dir_argument(self):
        """Test --output-dir argument is recognized."""
        from praisonai.cli.features.skills import add_skills_parser
        import argparse
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='skills_command')
        add_skills_parser(subparsers)
        
        # Test with --output-dir
        args = parser.parse_args(['create', '--name', 'test', '--output-dir', '/tmp/test'])
        assert args.output_dir == '/tmp/test'
    
    def test_author_argument(self):
        """Test --author argument is recognized."""
        from praisonai.cli.features.skills import add_skills_parser
        import argparse
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='skills_command')
        add_skills_parser(subparsers)
        
        args = parser.parse_args(['create', '--name', 'test', '--author', 'myteam'])
        assert args.author == 'myteam'
    
    def test_license_argument(self):
        """Test --license argument is recognized."""
        from praisonai.cli.features.skills import add_skills_parser
        import argparse
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='skills_command')
        add_skills_parser(subparsers)
        
        args = parser.parse_args(['create', '--name', 'test', '--license', 'MIT'])
        assert args.license == 'MIT'
    
    def test_compatibility_argument(self):
        """Test --compatibility argument is recognized."""
        from praisonai.cli.features.skills import add_skills_parser
        import argparse
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='skills_command')
        add_skills_parser(subparsers)
        
        args = parser.parse_args(['create', '--name', 'test', '--compatibility', 'Python 3.8+'])
        assert args.compatibility == 'Python 3.8+'
    
    def test_template_argument(self):
        """Test --template argument is recognized."""
        from praisonai.cli.features.skills import add_skills_parser
        import argparse
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='skills_command')
        add_skills_parser(subparsers)
        
        args = parser.parse_args(['create', '--name', 'test', '--template'])
        assert args.template == True
    
    def test_prompt_argument_for_ai_generation(self):
        """Test prompt argument for AI generation."""
        from praisonai.cli.features.skills import add_skills_parser
        import argparse
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='skills_command')
        add_skills_parser(subparsers)
        
        # Prompt can be positional or via --description
        args = parser.parse_args(['create', '--name', 'test', '--description', 'Process CSV files'])
        assert args.description == 'Process CSV files'


class TestMultiAgentCLI:
    """Tests for multi-agent CLI command."""
    
    def test_agents_command_exists(self):
        """Test that agents command is recognized."""
        # This will be implemented after skills fixes
        pass
    
    def test_define_multiple_agents(self):
        """Test defining multiple agents with instructions and tools."""
        # This will be implemented after skills fixes
        pass


class TestAnthropicSkillsAPI:
    """Tests for Anthropic Skills API integration."""
    
    def test_upload_skill_command(self):
        """Test uploading skill to Anthropic."""
        # This will be implemented after skills fixes
        pass
    
    def test_list_skills_command(self):
        """Test listing skills from Anthropic."""
        # This will be implemented after skills fixes
        pass
