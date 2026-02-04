"""
Unit tests for Feature Parity Tracker.

Tests the Python and TypeScript feature extractors and the parity tracker generator.
"""

import json
import tempfile
from pathlib import Path

import pytest


class TestPythonFeatureExtractor:
    """Tests for PythonFeatureExtractor."""
    
    def test_extract_lazy_imports(self):
        """Test extraction of _LAZY_IMPORTS dictionary."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor
        
        # Create a mock __init__.py with _LAZY_IMPORTS
        mock_init = '''
_LAZY_IMPORTS = {
    'Agent': ('praisonaiagents.agent.agent', 'Agent'),
    'Tool': ('praisonaiagents.tools.base', 'Tool'),
}
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            init_file = pkg_dir / "__init__.py"
            init_file.write_text(mock_init)
            
            # Also create wrapper structure
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            extractor = PythonFeatureExtractor(Path(tmpdir))
            lazy_imports = extractor._extract_lazy_imports(init_file)
            
            assert 'Agent' in lazy_imports
            assert lazy_imports['Agent'] == ('praisonaiagents.agent.agent', 'Agent')
            assert 'Tool' in lazy_imports
    
    def test_extract_all_exports(self):
        """Test extraction of __all__ list."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor
        
        mock_init = '''
__all__ = [
    'Agent',
    'Tool',
    'Memory',
]
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            init_file = pkg_dir / "__init__.py"
            init_file.write_text(mock_init)
            
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            extractor = PythonFeatureExtractor(Path(tmpdir))
            all_exports = extractor._extract_all_exports(init_file)
            
            assert 'Agent' in all_exports
            assert 'Tool' in all_exports
            assert 'Memory' in all_exports
    
    def test_categorize_module_path(self):
        """Test categorization of module paths."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal structure
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            extractor = PythonFeatureExtractor(Path(tmpdir))
            
            assert extractor._categorize('praisonaiagents.agent.agent') == 'agent'
            assert extractor._categorize('praisonaiagents.tools.base') == 'tools'
            assert extractor._categorize('praisonaiagents.memory.memory') == 'memory'
            assert extractor._categorize('praisonaiagents.workflows') == 'workflows'
            assert extractor._categorize('praisonaiagents.unknown') == 'other'
    
    def test_infer_kind(self):
        """Test inference of export kind from name."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            extractor = PythonFeatureExtractor(Path(tmpdir))
            
            assert extractor._infer_kind('Agent') == 'class'
            assert extractor._infer_kind('MemoryConfig') == 'type'
            assert extractor._infer_kind('ToolResult') == 'type'
            assert extractor._infer_kind('HandoffError') == 'type'
            assert extractor._infer_kind('get_tool') == 'function'
            assert extractor._infer_kind('create_agent') == 'function'
            assert extractor._infer_kind('RECOMMENDED_PROMPT_PREFIX') == 'constant'
    
    def test_extract_cli_features(self):
        """Test extraction of CLI features from wrapper."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("_LAZY_IMPORTS = {}")
            
            features_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            features_dir.mkdir(parents=True)
            
            # Create some feature files
            (features_dir / "chat.py").write_text("# chat feature")
            (features_dir / "code.py").write_text("# code feature")
            (features_dir / "_internal.py").write_text("# internal, should be ignored")
            
            extractor = PythonFeatureExtractor(Path(tmpdir))
            cli_features = extractor._extract_cli_features()
            
            assert 'chat' in cli_features
            assert 'code' in cli_features
            assert '_internal' not in cli_features


class TestTypeScriptFeatureExtractor:
    """Tests for TypeScriptFeatureExtractor."""
    
    def test_extract_exports(self):
        """Test extraction of TypeScript exports."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor
        
        mock_index = '''
export { Agent, ImageAgent } from './agent';
export { Tool, BaseTool } from './tools';
export type { AgentConfig, ToolConfig } from './types';
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            index_file = ts_dir / "index.ts"
            index_file.write_text(mock_index)
            
            extractor = TypeScriptFeatureExtractor(Path(tmpdir))
            features = extractor.extract()
            
            export_names = {e.name for e in features.exports}
            assert 'Agent' in export_names
            assert 'ImageAgent' in export_names
            assert 'Tool' in export_names
            assert 'BaseTool' in export_names
            assert 'AgentConfig' in export_names
            assert 'ToolConfig' in export_names
    
    def test_parse_export_names_with_alias(self):
        """Test parsing export names with 'as' alias."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            
            extractor = TypeScriptFeatureExtractor(Path(tmpdir))
            
            names = extractor._parse_export_names("Agent, Tool as MyTool, Memory")
            assert names == ['Agent', 'MyTool', 'Memory']
    
    def test_categorize_source_path(self):
        """Test categorization of TypeScript source paths."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            
            extractor = TypeScriptFeatureExtractor(Path(tmpdir))
            
            assert extractor._categorize('./agent') == 'agent'
            assert extractor._categorize('./agent/index') == 'agent'
            assert extractor._categorize('./tools') == 'tools'
            assert extractor._categorize('./memory') == 'memory'
            assert extractor._categorize('./unknown') == 'other'


class TestParityTrackerGenerator:
    """Tests for ParityTrackerGenerator."""
    
    def test_generate_structure(self):
        """Test that generated tracker has correct structure."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal Python SDK structure
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text('''
_LAZY_IMPORTS = {
    'Agent': ('praisonaiagents.agent.agent', 'Agent'),
}
''')
            
            # Create minimal TypeScript SDK structure
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            (ts_dir / "index.ts").write_text("export { Agent } from './agent';")
            
            # Create wrapper structure
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            generator = ParityTrackerGenerator(Path(tmpdir))
            tracker = generator.generate()
            
            # Check structure
            assert 'version' in tracker
            assert 'lastUpdated' in tracker
            assert 'summary' in tracker
            assert 'pythonCoreSDK' in tracker
            assert 'pythonWrapper' in tracker
            assert 'typescriptSDK' in tracker
            assert 'gapMatrix' in tracker
    
    def test_summary_counts(self):
        """Test that summary counts are correct."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text('''
_LAZY_IMPORTS = {
    'Agent': ('praisonaiagents.agent.agent', 'Agent'),
    'Tool': ('praisonaiagents.tools.base', 'Tool'),
    'Memory': ('praisonaiagents.memory.memory', 'Memory'),
}
''')
            
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            (ts_dir / "index.ts").write_text("export { Agent } from './agent';")
            
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            (wrapper_dir / "chat.py").write_text("")
            
            generator = ParityTrackerGenerator(Path(tmpdir))
            tracker = generator.generate()
            
            assert tracker['summary']['pythonCoreFeatures'] == 3
            assert tracker['summary']['typescriptFeatures'] == 1
            assert tracker['summary']['gapCount'] == 2  # Tool and Memory missing
            assert tracker['summary']['pythonWrapperFeatures'] == 1  # chat
    
    def test_gap_matrix_status(self):
        """Test that gap matrix correctly identifies DONE vs TODO."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text('''
_LAZY_IMPORTS = {
    'Agent': ('praisonaiagents.agent.agent', 'Agent'),
    'Tool': ('praisonaiagents.tools.base', 'Tool'),
}
''')
            
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            (ts_dir / "index.ts").write_text("export { Agent } from './agent';")
            
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            generator = ParityTrackerGenerator(Path(tmpdir))
            tracker = generator.generate()
            
            # Find Agent and Tool in gap matrix
            all_gaps = []
            for gaps in tracker['gapMatrix'].values():
                all_gaps.extend(gaps)
            
            agent_gap = next(g for g in all_gaps if g['feature'] == 'Agent')
            tool_gap = next(g for g in all_gaps if g['feature'] == 'Tool')
            
            assert agent_gap['status'] == 'DONE'
            assert agent_gap['typescript'] is True
            assert tool_gap['status'] == 'TODO'
            assert tool_gap['typescript'] is False
    
    def test_write_typescript_creates_file(self):
        """Test that write_typescript creates the output file."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("_LAZY_IMPORTS = {}")
            
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            (ts_dir / "index.ts").write_text("")
            
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            generator = ParityTrackerGenerator(Path(tmpdir))
            result = generator.write_typescript()
            
            assert result == 0
            assert generator.ts_output.exists()
            
            # Verify JSON is valid
            with open(generator.ts_output) as f:
                data = json.load(f)
            assert 'version' in data
    
    def test_write_rust_creates_file(self):
        """Test that write_rust creates the output file."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("_LAZY_IMPORTS = {}")
            
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            (ts_dir / "index.ts").write_text("")
            
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            # Create rust dir
            rust_dir = Path(tmpdir) / "src" / "praisonai-rust"
            rust_dir.mkdir(parents=True)
            
            generator = ParityTrackerGenerator(Path(tmpdir))
            result = generator.write_rust()
            
            assert result == 0
            assert generator.rust_output.exists()
            
            with open(generator.rust_output) as f:
                data = json.load(f)
            assert data['status'] == 'NOT_STARTED'


class TestGenerateParityTracker:
    """Tests for the generate_parity_tracker function."""
    
    def test_stdout_mode(self, capsys):
        """Test stdout mode prints JSON."""
        from praisonai._dev.parity.generator import generate_parity_tracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("_LAZY_IMPORTS = {}")
            
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            (ts_dir / "index.ts").write_text("")
            
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            result = generate_parity_tracker(
                repo_root=Path(tmpdir),
                stdout=True
            )
            
            assert result == 0
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert 'version' in data
    
    def test_check_mode_up_to_date(self):
        """Test check mode returns 0 when up to date."""
        from praisonai._dev.parity.generator import generate_parity_tracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("_LAZY_IMPORTS = {}")
            
            ts_dir = Path(tmpdir) / "src" / "praisonai-ts" / "src"
            ts_dir.mkdir(parents=True)
            (ts_dir / "index.ts").write_text("")
            
            wrapper_dir = Path(tmpdir) / "src" / "praisonai" / "praisonai" / "cli" / "features"
            wrapper_dir.mkdir(parents=True)
            
            # First generate
            generate_parity_tracker(repo_root=Path(tmpdir), target='ts')
            
            # Then check
            result = generate_parity_tracker(
                repo_root=Path(tmpdir),
                target='ts',
                check=True
            )
            
            assert result == 0


class TestRealExtraction:
    """Integration tests using the real PraisonAI repository."""
    
    @pytest.mark.skipif(
        not Path("/Users/praison/praisonai-package").exists(),
        reason="Real repo not available"
    )
    def test_extract_real_python_features(self):
        """Test extraction from real Python SDK."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor
        
        extractor = PythonFeatureExtractor()
        features = extractor.extract()
        
        # Should have many exports
        assert len(features.exports) > 50
        
        # Should have key exports
        export_names = {e.name for e in features.exports}
        assert 'Agent' in export_names
        assert 'Tool' in export_names or 'tool' in export_names
        assert 'Memory' in export_names
        
        # Should have modules
        assert len(features.modules) > 5
        assert 'agent' in features.modules
    
    @pytest.mark.skipif(
        not Path("/Users/praison/praisonai-package").exists(),
        reason="Real repo not available"
    )
    def test_extract_real_typescript_features(self):
        """Test extraction from real TypeScript SDK."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor
        
        extractor = TypeScriptFeatureExtractor()
        features = extractor.extract()
        
        # Should have exports
        assert len(features.exports) > 10
        
        # Should have key exports
        export_names = {e.name for e in features.exports}
        assert 'Agent' in export_names
    
    @pytest.mark.skipif(
        not Path("/Users/praison/praisonai-package").exists(),
        reason="Real repo not available"
    )
    def test_generate_real_tracker(self):
        """Test generating tracker from real repository."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator
        
        generator = ParityTrackerGenerator()
        tracker = generator.generate()
        
        # Should have valid structure
        assert tracker['summary']['pythonCoreFeatures'] > 50
        assert tracker['summary']['typescriptFeatures'] > 10
        
        # Gap count should be reasonable
        assert tracker['summary']['gapCount'] >= 0
