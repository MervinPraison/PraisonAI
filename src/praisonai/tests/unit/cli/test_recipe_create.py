"""
Tests for recipe create and optimize commands.

TDD: These tests are written FIRST before implementation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile


class TestRecipeCreatorFolderName:
    """Tests for folder name generation."""
    
    def test_generate_folder_name_kebab_case(self):
        """Test that folder names are kebab-case."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        creator = RecipeCreator()
        name = creator.generate_folder_name("Build a Web Scraper for News")
        
        assert "-" in name or name.islower()
        assert " " not in name
        assert name.islower()
    
    def test_generate_folder_name_max_length(self):
        """Test that folder names are max 50 chars."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        creator = RecipeCreator()
        long_goal = "Build a comprehensive web scraper that extracts news articles from multiple sources and summarizes them"
        name = creator.generate_folder_name(long_goal)
        
        assert len(name) <= 50
    
    def test_generate_folder_name_removes_special_chars(self):
        """Test that special characters are removed."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        creator = RecipeCreator()
        name = creator.generate_folder_name("Build a scraper! @#$%")
        
        assert "@" not in name
        assert "#" not in name
        assert "!" not in name


class TestRecipeCreatorAgentsYaml:
    """Tests for agents.yaml generation."""
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator._get_litellm')
    def test_generate_agents_yaml_calls_llm(self, mock_get_litellm):
        """Test that LLM is called for agents.yaml generation."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """framework: praisonai
topic: "Web Scraper"
agents:
  scraper:
    role: Web Scraper
    goal: Scrape web pages
    backstory: Expert at web scraping
"""
        mock_litellm.completion.return_value = mock_response
        mock_get_litellm.return_value = mock_litellm
        
        creator = RecipeCreator()
        yaml_content = creator.generate_agents_yaml("Build a web scraper")
        
        mock_litellm.completion.assert_called_once()
        assert "framework: praisonai" in yaml_content or "agents:" in yaml_content
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator._get_litellm')
    def test_generate_agents_yaml_includes_sdk_knowledge(self, mock_get_litellm):
        """Test that SDK knowledge prompt is included."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "framework: praisonai\nagents: {}"
        mock_litellm.completion.return_value = mock_response
        mock_get_litellm.return_value = mock_litellm
        
        creator = RecipeCreator()
        creator.generate_agents_yaml("Build a web scraper")
        
        # Check that the prompt contains SDK knowledge
        call_args = mock_litellm.completion.call_args
        messages = call_args.kwargs.get('messages', call_args[1].get('messages', []))
        prompt = str(messages)
        
        # Should mention key SDK concepts
        assert "agent" in prompt.lower() or "tool" in prompt.lower()


class TestRecipeCreatorToolsPy:
    """Tests for tools.py generation."""
    
    def test_generate_tools_py_imports_correct_tools(self):
        """Test that tools.py imports the right tools."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        creator = RecipeCreator()
        tools_content = creator.generate_tools_py(["tavily_search", "read_file", "write_file"])
        
        assert "tavily" in tools_content.lower() or "search" in tools_content.lower()
        assert "def " in tools_content or "import " in tools_content
    
    def test_generate_tools_py_valid_python(self):
        """Test that generated tools.py is valid Python."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        creator = RecipeCreator()
        tools_content = creator.generate_tools_py(["read_file"])
        
        # Should be valid Python (no syntax errors)
        compile(tools_content, '<string>', 'exec')


class TestRecipeCreatorCreate:
    """Tests for the main create method."""
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator._get_litellm')
    def test_create_returns_path(self, mock_get_litellm):
        """Test that create() returns the recipe path."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """framework: praisonai
topic: "Test"
agents:
  test_agent:
    role: Tester
    goal: Test things
    backstory: Expert tester
"""
        mock_litellm.completion.return_value = mock_response
        mock_get_litellm.return_value = mock_litellm
        
        with tempfile.TemporaryDirectory() as tmpdir:
            creator = RecipeCreator()
            path = creator.create("Build a test recipe", output_dir=Path(tmpdir))
            
            assert path.exists()
            assert path.is_dir()
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator._get_litellm')
    def test_create_creates_all_files(self, mock_get_litellm):
        """Test that create() creates all required files."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """framework: praisonai
topic: "Test"
agents:
  test_agent:
    role: Tester
    goal: Test things
    backstory: Expert tester
"""
        mock_litellm.completion.return_value = mock_response
        mock_get_litellm.return_value = mock_litellm
        
        with tempfile.TemporaryDirectory() as tmpdir:
            creator = RecipeCreator()
            path = creator.create("Build a test recipe", output_dir=Path(tmpdir))
            
            assert (path / "agents.yaml").exists()
            assert (path / "TEMPLATE.yaml").exists()
            assert (path / "tools.py").exists()


class TestRecipeOptimizer:
    """Tests for RecipeOptimizer class."""
    
    def test_should_continue_respects_threshold(self):
        """Test that optimization stops when score threshold is reached."""
        from praisonai.cli.features.recipe_optimizer import RecipeOptimizer
        
        optimizer = RecipeOptimizer(score_threshold=8.0, max_iterations=3)
        
        # Mock report with high score
        mock_report = MagicMock()
        mock_report.overall_score = 9.0
        
        assert optimizer.should_continue(mock_report, iteration=1) is False
    
    def test_should_continue_respects_max_iterations(self):
        """Test that optimization stops at max iterations."""
        from praisonai.cli.features.recipe_optimizer import RecipeOptimizer
        
        optimizer = RecipeOptimizer(score_threshold=8.0, max_iterations=3)
        
        # Mock report with low score
        mock_report = MagicMock()
        mock_report.overall_score = 5.0
        
        assert optimizer.should_continue(mock_report, iteration=3) is False
        assert optimizer.should_continue(mock_report, iteration=2) is True


class TestCmdCreate:
    """Tests for cmd_create CLI command."""
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator')
    def test_cmd_create_parses_goal(self, mock_creator_class):
        """Test that cmd_create parses the goal argument."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        mock_creator = MagicMock()
        mock_creator.create.return_value = Path("/tmp/test-recipe")
        mock_creator_class.return_value = mock_creator
        
        handler = RecipeHandler()
        
        with patch.object(handler, '_print_success'):
            handler.cmd_create(["Build a web scraper", "--no-optimize"])
        
        mock_creator.create.assert_called_once()
        call_args = mock_creator.create.call_args
        assert "Build a web scraper" in str(call_args)


class TestRecipeCreatorCustomization:
    """Tests for recipe creation customization options."""
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator._get_litellm')
    def test_create_with_agents_parameter(self, mock_get_litellm):
        """Test that agents parameter overrides LLM generation."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """framework: praisonai
topic: "Test"
agents:
  researcher:
    role: AI Researcher
    goal: Research topics
    backstory: Expert researcher
"""
        mock_litellm.completion.return_value = mock_response
        mock_get_litellm.return_value = mock_litellm
        
        with tempfile.TemporaryDirectory() as tmpdir:
            creator = RecipeCreator()
            
            # Specify custom agents
            custom_agents = {
                "my_agent": {
                    "role": "Custom Role",
                    "goal": "Custom Goal",
                    "backstory": "Custom backstory"
                }
            }
            
            path = creator.create(
                "Test goal",
                output_dir=Path(tmpdir),
                agents=custom_agents
            )
            
            # Read the generated agents.yaml
            agents_yaml = (path / "agents.yaml").read_text()
            
            # Should contain custom agent
            assert "my_agent" in agents_yaml or "Custom Role" in agents_yaml
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator._get_litellm')
    def test_create_with_tools_parameter(self, mock_get_litellm):
        """Test that tools parameter assigns tools to agents."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """framework: praisonai
topic: "Test"
agents:
  researcher:
    role: Researcher
    goal: Research
    backstory: Expert
    tools:
      - internet_search
"""
        mock_litellm.completion.return_value = mock_response
        mock_get_litellm.return_value = mock_litellm
        
        with tempfile.TemporaryDirectory() as tmpdir:
            creator = RecipeCreator()
            
            # Specify custom tools per agent
            custom_tools = {
                "researcher": ["tavily_search", "arxiv_search"]
            }
            
            path = creator.create(
                "Research AI",
                output_dir=Path(tmpdir),
                tools=custom_tools
            )
            
            # Read the generated agents.yaml
            agents_yaml = (path / "agents.yaml").read_text()
            
            # Should contain specified tools
            assert "tavily_search" in agents_yaml or "arxiv_search" in agents_yaml
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator._get_litellm')
    def test_create_with_agent_types_parameter(self, mock_get_litellm):
        """Test that agent_types parameter sets agent type."""
        from praisonai.cli.features.recipe_creator import RecipeCreator
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """framework: praisonai
topic: "Test"
agents:
  artist:
    role: Artist
    goal: Create images
    backstory: Expert artist
    type: image
"""
        mock_litellm.completion.return_value = mock_response
        mock_get_litellm.return_value = mock_litellm
        
        with tempfile.TemporaryDirectory() as tmpdir:
            creator = RecipeCreator()
            
            # Specify agent types
            custom_types = {
                "artist": "image"
            }
            
            path = creator.create(
                "Generate images",
                output_dir=Path(tmpdir),
                agent_types=custom_types
            )
            
            # Read the generated agents.yaml
            agents_yaml = (path / "agents.yaml").read_text()
            
            # Should contain type specification
            assert "type:" in agents_yaml or "image" in agents_yaml


class TestCmdCreateCustomization:
    """Tests for cmd_create CLI customization options."""
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator')
    def test_cmd_create_with_agents_option(self, mock_creator_class):
        """Test that --agents CLI option is parsed correctly."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        mock_creator = MagicMock()
        mock_creator.create.return_value = Path("/tmp/test-recipe")
        mock_creator_class.return_value = mock_creator
        
        handler = RecipeHandler()
        
        with patch.object(handler, '_print_success'):
            handler.cmd_create([
                "Build a research tool",
                "--agents", "researcher:role=AI Researcher,goal=Find papers",
                "--no-optimize"
            ])
        
        mock_creator.create.assert_called_once()
        call_kwargs = mock_creator.create.call_args.kwargs
        assert 'agents' in call_kwargs or 'agents' in str(mock_creator.create.call_args)
    
    @patch('praisonai.cli.features.recipe_creator.RecipeCreator')
    def test_cmd_create_with_tools_option(self, mock_creator_class):
        """Test that --tools CLI option is parsed correctly."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        mock_creator = MagicMock()
        mock_creator.create.return_value = Path("/tmp/test-recipe")
        mock_creator_class.return_value = mock_creator
        
        handler = RecipeHandler()
        
        with patch.object(handler, '_print_success'):
            handler.cmd_create([
                "Build a research tool",
                "--tools", "researcher:internet_search,arxiv",
                "--no-optimize"
            ])
        
        mock_creator.create.assert_called_once()
        call_kwargs = mock_creator.create.call_args.kwargs
        assert 'tools' in call_kwargs or 'tools' in str(mock_creator.create.call_args)


class TestCmdOptimize:
    """Tests for cmd_optimize CLI command."""
    
    @patch('praisonai.cli.features.recipe_optimizer.RecipeOptimizer')
    def test_cmd_optimize_parses_args(self, mock_optimizer_class):
        """Test that cmd_optimize parses name and target."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        mock_optimizer = MagicMock()
        mock_report = MagicMock()
        mock_report.overall_score = 8.5
        mock_optimizer.optimize.return_value = mock_report
        mock_optimizer_class.return_value = mock_optimizer
        
        handler = RecipeHandler()
        
        # Create a temp directory to simulate recipe path
        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "test-recipe"
            recipe_path.mkdir()
            (recipe_path / "agents.yaml").write_text("framework: praisonai")
            
            with patch.object(handler, '_print_success'):
                with patch('pathlib.Path.cwd', return_value=Path(tmpdir)):
                    handler.cmd_optimize(["test-recipe", "improve error handling"])
        
        mock_optimizer.optimize.assert_called_once()
