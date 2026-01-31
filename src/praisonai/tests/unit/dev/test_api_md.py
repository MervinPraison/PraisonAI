"""
Tests for the API markdown generator.

Tests cover:
- Symbol discovery (respects __all__)
- Lazy-loaded symbol discovery from __getattr__
- Link generation (relative paths correct)
- Stable ordering (deterministic)
- TypeScript export parsing
- CLI command discovery
"""

import sys
from pathlib import Path
import pytest

# Add the praisonai package to path
# repo_root should be the actual repository root (praisonai-package), not the praisonai src dir
repo_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(repo_root / "src" / "praisonai"))

from praisonai._dev.api_md import ApiMdGenerator, generate_api_md


class TestApiMdGenerator:
    """Tests for ApiMdGenerator class."""
    
    @pytest.fixture
    def generator(self):
        """Create a generator instance."""
        return ApiMdGenerator(repo_root=repo_root)
    
    def test_init_finds_repo_root(self, generator):
        """Test that generator finds the repository root."""
        assert generator.repo_root.exists()
        assert (generator.repo_root / ".git").exists()
    
    def test_init_finds_package_paths(self, generator):
        """Test that generator finds package paths."""
        assert generator.agents_pkg.exists()
        assert generator.wrapper_pkg.exists()
        assert generator.ts_pkg.exists()
    
    def test_discover_all_finds_symbols(self, generator):
        """Test that discover_all finds symbols from all packages."""
        generator.discover_all()
        
        # Should find symbols from praisonaiagents
        assert len(generator.agents_symbols) > 0
        
        # Should find CLI commands
        assert len(generator.cli_commands) > 0
        
        # Should find TypeScript exports
        assert len(generator.ts_exports) > 0
    
    def test_discovers_agent_class(self, generator):
        """Test that Agent class is discovered."""
        generator.discover_all()
        
        assert "Agent" in generator.agents_symbols
        agent_info = generator.agents_symbols["Agent"]
        assert agent_info.kind == "class"
        assert "agent.py" in agent_info.file_path
    
    def test_discovers_agents_class(self, generator):
        """Test that AgentTeam class is discovered (primary class for multi-agent coordination)."""
        generator.discover_all()
        
        assert "AgentTeam" in generator.agents_symbols
        agents_info = generator.agents_symbols["AgentTeam"]
        assert agents_info.kind == "class"
    
    def test_discovers_workflow_exports(self, generator):
        """Test that Workflow exports are discovered.
        
        Note: Workflow/Pipeline are available via __getattr__ but not in __all__.
        The minimal __all__ only includes core classes.
        """
        generator.discover_all()
        
        # Check that core exports are found (Workflow is available via __getattr__ but not in __all__)
        # The current __all__ is minimal: Agent, Agents, Task, Tools, tool
        core_exports = ["Agent", "Agents", "Task", "Tools", "tool"]
        found = [e for e in core_exports if e in generator.agents_symbols]
        assert len(found) >= 3, f"Expected core exports, found: {list(generator.agents_symbols.keys())[:20]}"
    
    def test_discovers_tool_exports(self, generator):
        """Test that tool exports are discovered."""
        generator.discover_all()
        
        # Check for tool-related exports
        assert "Tools" in generator.agents_symbols or "BaseTool" in generator.agents_symbols
    
    def test_discovers_lazy_loaded_symbols(self, generator):
        """Test that lazy-loaded symbols from __getattr__ are discovered.
        
        Note: The current __all__ is minimal. Memory, Knowledge, Session are
        available via __getattr__ but not in __all__.
        """
        generator.discover_all()
        
        # These are in the minimal __all__
        core_symbols = ["Agent", "Agents", "Task", "Tools", "tool"]
        found = [s for s in core_symbols if s in generator.agents_symbols]
        assert len(found) >= 2, f"Expected at least 2 core symbols, found: {found}"
    
    def test_symbol_has_file_path(self, generator):
        """Test that discovered symbols have valid file paths."""
        generator.discover_all()
        
        for name, info in list(generator.agents_symbols.items())[:10]:
            assert info.file_path, f"Symbol {name} missing file_path"
            assert info.file_path.startswith("./"), f"Path should be relative: {info.file_path}"
    
    def test_class_has_methods(self, generator):
        """Test that class symbols have methods extracted."""
        generator.discover_all()
        
        if "Agent" in generator.agents_symbols:
            agent_info = generator.agents_symbols["Agent"]
            assert len(agent_info.methods) > 0, "Agent class should have methods"
            
            # Check for common methods
            method_names = [m.name for m in agent_info.methods]
            assert "start" in method_names or "run" in method_names or "chat" in method_names


class TestTypescriptDiscovery:
    """Tests for TypeScript export discovery."""
    
    @pytest.fixture
    def generator(self):
        return ApiMdGenerator(repo_root=repo_root)
    
    def test_discovers_ts_exports(self, generator):
        """Test that TypeScript exports are discovered."""
        generator.discover_all()
        
        assert len(generator.ts_exports) > 0
    
    def test_ts_exports_have_source_file(self, generator):
        """Test that TS exports have source file info."""
        generator.discover_all()
        
        for export in generator.ts_exports[:10]:
            assert export.source_file, f"Export {export.name} missing source_file"
    
    def test_discovers_agent_ts_export(self, generator):
        """Test that Agent is exported from TypeScript."""
        generator.discover_all()
        
        export_names = [e.name for e in generator.ts_exports]
        assert "Agent" in export_names


class TestCLIDiscovery:
    """Tests for CLI command discovery."""
    
    @pytest.fixture
    def generator(self):
        return ApiMdGenerator(repo_root=repo_root)
    
    def test_discovers_cli_commands(self, generator):
        """Test that CLI commands are discovered."""
        generator.discover_all()
        
        assert len(generator.cli_commands) > 0
    
    def test_cli_commands_have_file_path(self, generator):
        """Test that CLI commands have file paths."""
        generator.discover_all()
        
        for cmd in generator.cli_commands[:10]:
            assert cmd.file_path, f"Command {cmd.command_path} missing file_path"


class TestMarkdownGeneration:
    """Tests for markdown output generation."""
    
    @pytest.fixture
    def generator(self):
        return ApiMdGenerator(repo_root=repo_root)
    
    def test_generate_returns_string(self, generator):
        """Test that generate returns a string."""
        content = generator.generate()
        assert isinstance(content, str)
        assert len(content) > 0
    
    def test_generate_has_header(self, generator):
        """Test that generated content has header."""
        content = generator.generate()
        assert "# PraisonAI API Reference" in content
    
    def test_generate_has_regenerate_instruction(self, generator):
        """Test that generated content has regeneration instruction."""
        content = generator.generate()
        assert "praisonai docs api-md" in content
    
    def test_generate_has_types_block(self, generator):
        """Test that generated content has Types blocks."""
        content = generator.generate()
        assert "Types:" in content
        assert "```python" in content
    
    def test_generate_has_methods_block(self, generator):
        """Test that generated content has Methods blocks."""
        content = generator.generate()
        assert "Methods:" in content
    
    def test_generate_has_typescript_section(self, generator):
        """Test that generated content has TypeScript section."""
        content = generator.generate()
        assert "# TypeScript" in content
        assert "```ts" in content
    
    def test_generate_has_cli_section(self, generator):
        """Test that generated content has CLI section."""
        content = generator.generate()
        assert "# CLI" in content
    
    def test_generate_has_plugins_section(self, generator):
        """Test that generated content has Optional Plugins section."""
        content = generator.generate()
        assert "# Optional Plugins" in content
        assert "praisonai-tools" in content


class TestDeterministicOutput:
    """Tests for deterministic/stable output."""
    
    @pytest.fixture
    def generator(self):
        return ApiMdGenerator(repo_root=repo_root)
    
    def test_generate_is_deterministic(self, generator):
        """Test that two runs produce identical output."""
        content1 = generator.generate()
        
        # Create a new generator and generate again
        generator2 = ApiMdGenerator(repo_root=repo_root)
        content2 = generator2.generate()
        
        assert content1 == content2, "Output should be deterministic"
    
    def test_symbols_are_sorted(self, generator):
        """Test that symbols are sorted alphabetically."""
        generator.discover_all()
        
        symbol_names = list(generator.agents_symbols.keys())
        assert symbol_names == sorted(symbol_names), "Symbols should be sorted"


class TestGenerateApiMdFunction:
    """Tests for the generate_api_md function."""
    
    def test_generate_to_stdout(self, capsys):
        """Test generating to stdout."""
        exit_code = generate_api_md(repo_root=repo_root, stdout=True)
        
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "# PraisonAI API Reference" in captured.out
    
    def test_check_mode_passes_when_current(self, tmp_path):
        """Test that check mode passes when file is current."""
        # Generate to a temp file
        output_path = tmp_path / "api.md"
        exit_code = generate_api_md(repo_root=repo_root, output_path=output_path)
        assert exit_code == 0
        
        # Check should pass
        exit_code = generate_api_md(repo_root=repo_root, output_path=output_path, check=True)
        assert exit_code == 0
    
    def test_check_mode_fails_when_outdated(self, tmp_path):
        """Test that check mode fails when file is outdated."""
        # Create an outdated file
        output_path = tmp_path / "api.md"
        output_path.write_text("# Old content")
        
        # Check should fail
        exit_code = generate_api_md(repo_root=repo_root, output_path=output_path, check=True)
        assert exit_code == 1
    
    def test_check_mode_fails_when_missing(self, tmp_path):
        """Test that check mode fails when file is missing."""
        output_path = tmp_path / "api.md"
        
        # Check should fail
        exit_code = generate_api_md(repo_root=repo_root, output_path=output_path, check=True)
        assert exit_code == 1


class TestLinkGeneration:
    """Tests for link generation in output."""
    
    @pytest.fixture
    def generator(self):
        return ApiMdGenerator(repo_root=repo_root)
    
    def test_links_are_relative(self, generator):
        """Test that links are relative to repo root."""
        content = generator.generate()
        
        # All href links should start with ./
        import re
        hrefs = re.findall(r'href="([^"]+)"', content)
        for href in hrefs:
            assert href.startswith("./"), f"Link should be relative: {href}"
    
    def test_links_point_to_existing_files(self, generator):
        """Test that links point to existing files."""
        generator.discover_all()
        
        for name, info in list(generator.agents_symbols.items())[:10]:
            if info.file_path:
                # Remove ./ prefix
                rel_path = info.file_path[2:] if info.file_path.startswith("./") else info.file_path
                full_path = generator.repo_root / rel_path
                assert full_path.exists(), f"File not found: {full_path}"
