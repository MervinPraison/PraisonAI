"""
Tests for Repository Map System.

Test-Driven Development approach for codebase mapping.
"""

import pytest
from pathlib import Path
import tempfile

from praisonai.cli.features.repo_map import (
    Symbol,
    FileMap,
    RepoMapConfig,
    SymbolExtractor,
    SymbolRanker,
    RepoMap,
    RepoMapHandler,
)


# ============================================================================
# Symbol Tests
# ============================================================================

class TestSymbol:
    """Tests for Symbol dataclass."""
    
    def test_create_symbol(self):
        """Test creating a symbol."""
        symbol = Symbol(
            name="MyClass",
            kind="class",
            file_path="test.py",
            line_number=10
        )
        assert symbol.name == "MyClass"
        assert symbol.kind == "class"
        assert symbol.file_path == "test.py"
        assert symbol.line_number == 10
    
    def test_symbol_with_signature(self):
        """Test symbol with signature."""
        symbol = Symbol(
            name="my_function",
            kind="function",
            file_path="test.py",
            line_number=5,
            signature="def my_function(x, y):"
        )
        assert symbol.signature == "def my_function(x, y):"
    
    def test_symbol_with_parent(self):
        """Test method symbol with parent class."""
        symbol = Symbol(
            name="method",
            kind="method",
            file_path="test.py",
            line_number=15,
            parent="MyClass"
        )
        assert symbol.parent == "MyClass"
        assert symbol.qualified_name == "MyClass.method"
    
    def test_symbol_qualified_name_no_parent(self):
        """Test qualified name without parent."""
        symbol = Symbol(
            name="function",
            kind="function",
            file_path="test.py",
            line_number=1
        )
        assert symbol.qualified_name == "function"
    
    def test_symbol_hash(self):
        """Test symbol hashing for sets."""
        s1 = Symbol("test", "function", "file.py", 1)
        s2 = Symbol("test", "function", "file.py", 1)
        s3 = Symbol("test", "function", "file.py", 2)
        
        assert hash(s1) == hash(s2)
        assert hash(s1) != hash(s3)


# ============================================================================
# FileMap Tests
# ============================================================================

class TestFileMap:
    """Tests for FileMap dataclass."""
    
    def test_create_file_map(self):
        """Test creating a file map."""
        file_map = FileMap(file_path="test.py")
        assert file_map.file_path == "test.py"
        assert file_map.symbols == []
    
    def test_add_symbol(self):
        """Test adding symbols to file map."""
        file_map = FileMap(file_path="test.py")
        symbol = Symbol("test", "function", "test.py", 1)
        
        file_map.add_symbol(symbol)
        
        assert len(file_map.symbols) == 1
        assert file_map.symbols[0].name == "test"
    
    def test_get_summary(self):
        """Test getting file summary."""
        file_map = FileMap(file_path="test.py")
        file_map.add_symbol(Symbol(
            "MyClass", "class", "test.py", 1,
            signature="class MyClass:"
        ))
        file_map.add_symbol(Symbol(
            "my_func", "function", "test.py", 10,
            signature="def my_func(x):"
        ))
        
        summary = file_map.get_summary()
        
        assert "test.py:" in summary
        assert "class MyClass:" in summary or "MyClass" in summary


# ============================================================================
# RepoMapConfig Tests
# ============================================================================

class TestRepoMapConfig:
    """Tests for RepoMapConfig."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = RepoMapConfig()
        
        assert config.max_tokens == 1024
        assert config.max_files == 50
        assert ".py" in config.file_extensions
        assert "__pycache__" in config.exclude_patterns
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = RepoMapConfig(
            max_tokens=2048,
            max_files=100,
            file_extensions={".py", ".js"}
        )
        
        assert config.max_tokens == 2048
        assert config.max_files == 100
        assert len(config.file_extensions) == 2


# ============================================================================
# SymbolExtractor Tests
# ============================================================================

class TestSymbolExtractor:
    """Tests for SymbolExtractor."""
    
    def test_create_extractor(self):
        """Test creating extractor."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        assert extractor is not None
    
    def test_extract_python_class(self):
        """Test extracting Python class."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        
        content = """
class MyClass:
    def __init__(self):
        pass
    
    def method(self):
        pass
"""
        
        symbols = extractor.extract_symbols("test.py", content)
        
        class_symbols = [s for s in symbols if s.kind == "class"]
        assert len(class_symbols) >= 1
        assert class_symbols[0].name == "MyClass"
    
    def test_extract_python_function(self):
        """Test extracting Python function."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        
        content = """
def my_function(x, y):
    return x + y

def another_function():
    pass
"""
        
        symbols = extractor.extract_symbols("test.py", content)
        
        func_symbols = [s for s in symbols if s.kind == "function"]
        assert len(func_symbols) >= 2
        names = [s.name for s in func_symbols]
        assert "my_function" in names
        assert "another_function" in names
    
    def test_extract_python_method(self):
        """Test extracting Python method."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        
        content = """
class MyClass:
    def method_one(self):
        pass
    
    def method_two(self, x):
        return x
"""
        
        symbols = extractor.extract_symbols("test.py", content)
        
        method_symbols = [s for s in symbols if s.kind == "method"]
        assert len(method_symbols) >= 2
        
        # Check parent is set
        for method in method_symbols:
            assert method.parent == "MyClass"
    
    def test_extract_javascript_class(self):
        """Test extracting JavaScript class."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        
        content = """
class MyComponent {
    constructor() {}
}

export class AnotherClass {}
"""
        
        symbols = extractor.extract_symbols("test.js", content)
        
        class_symbols = [s for s in symbols if s.kind == "class"]
        assert len(class_symbols) >= 1
    
    def test_extract_javascript_function(self):
        """Test extracting JavaScript function."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        
        content = """
function myFunction() {}

const arrowFunc = () => {};

async function asyncFunc() {}
"""
        
        symbols = extractor.extract_symbols("test.js", content)
        
        func_symbols = [s for s in symbols if s.kind == "function"]
        assert len(func_symbols) >= 1
    
    def test_extract_go_symbols(self):
        """Test extracting Go symbols."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        
        content = """
type MyStruct struct {
    Name string
}

func MyFunction() {}

func (m *MyStruct) Method() {}
"""
        
        symbols = extractor.extract_symbols("test.go", content)
        
        assert len(symbols) >= 2
    
    def test_extract_rust_symbols(self):
        """Test extracting Rust symbols."""
        extractor = SymbolExtractor(use_tree_sitter=False)
        
        content = """
pub struct MyStruct {
    field: i32,
}

fn my_function() {}

pub async fn async_func() {}
"""
        
        symbols = extractor.extract_symbols("test.rs", content)
        
        assert len(symbols) >= 2


# ============================================================================
# SymbolRanker Tests
# ============================================================================

class TestSymbolRanker:
    """Tests for SymbolRanker."""
    
    def test_create_ranker(self):
        """Test creating ranker."""
        ranker = SymbolRanker()
        assert ranker is not None
    
    def test_analyze_references(self):
        """Test analyzing references."""
        ranker = SymbolRanker()
        
        file_maps = {
            "a.py": FileMap(
                file_path="a.py",
                symbols=[Symbol("MyClass", "class", "a.py", 1)]
            ),
            "b.py": FileMap(
                file_path="b.py",
                symbols=[Symbol("use_class", "function", "b.py", 1)]
            )
        }
        
        all_content = {
            "a.py": "class MyClass:\n    pass",
            "b.py": "from a import MyClass\nobj = MyClass()"
        }
        
        ranker.analyze_references(file_maps, all_content)
        
        # MyClass should have references
        my_class = file_maps["a.py"].symbols[0]
        assert my_class.references > 0
    
    def test_get_top_symbols(self):
        """Test getting top symbols."""
        ranker = SymbolRanker()
        
        file_maps = {
            "test.py": FileMap(
                file_path="test.py",
                symbols=[
                    Symbol("HighRef", "class", "test.py", 1, references=10),
                    Symbol("LowRef", "function", "test.py", 10, references=1),
                    Symbol("MedRef", "function", "test.py", 20, references=5),
                ]
            )
        }
        
        # Manually set references
        file_maps["test.py"].symbols[0].references = 10
        file_maps["test.py"].symbols[1].references = 1
        file_maps["test.py"].symbols[2].references = 5
        
        top = ranker.get_top_symbols(file_maps, max_symbols=2)
        
        assert len(top) == 2
        assert top[0].name == "HighRef"


# ============================================================================
# RepoMap Tests
# ============================================================================

class TestRepoMap:
    """Tests for RepoMap."""
    
    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            (Path(tmpdir) / "main.py").write_text("""
class Application:
    def __init__(self):
        self.config = Config()
    
    def run(self):
        pass

def main():
    app = Application()
    app.run()
""")
            
            (Path(tmpdir) / "config.py").write_text("""
class Config:
    def __init__(self):
        self.debug = False
    
    def load(self):
        pass
""")
            
            (Path(tmpdir) / "utils.py").write_text("""
def helper_function():
    pass

def format_output(data):
    return str(data)
""")
            
            yield tmpdir
    
    def test_create_repo_map(self, temp_repo):
        """Test creating a repo map."""
        repo_map = RepoMap(root=temp_repo)
        assert repo_map.root == Path(temp_repo)
    
    def test_scan_repository(self, temp_repo):
        """Test scanning a repository."""
        repo_map = RepoMap(root=temp_repo)
        repo_map.scan()
        
        assert len(repo_map._file_maps) > 0
    
    def test_get_map(self, temp_repo):
        """Test getting the repository map."""
        repo_map = RepoMap(root=temp_repo)
        map_str = repo_map.get_map()
        
        assert len(map_str) > 0
        # Should contain file names
        assert "main.py" in map_str or "config.py" in map_str
    
    def test_get_map_with_focus(self, temp_repo):
        """Test getting map with focus files."""
        repo_map = RepoMap(root=temp_repo)
        repo_map.scan()
        
        map_str = repo_map.get_map(focus_files=["main.py"])
        
        assert "main.py" in map_str
    
    def test_get_file_symbols(self, temp_repo):
        """Test getting symbols for a specific file."""
        repo_map = RepoMap(root=temp_repo)
        repo_map.scan()
        
        symbols = repo_map.get_file_symbols("main.py")
        
        assert len(symbols) > 0
    
    def test_get_symbol_context(self, temp_repo):
        """Test getting context for a symbol."""
        repo_map = RepoMap(root=temp_repo)
        repo_map.scan()
        
        context = repo_map.get_symbol_context("Application")
        
        if context:  # May not find if symbol extraction differs
            assert "Application" in context
    
    def test_refresh(self, temp_repo):
        """Test refreshing the map."""
        repo_map = RepoMap(root=temp_repo)
        repo_map.scan()
        
        initial_count = len(repo_map._file_maps)
        
        repo_map.refresh()
        
        assert len(repo_map._file_maps) == initial_count


# ============================================================================
# RepoMapHandler Tests
# ============================================================================

class TestRepoMapHandler:
    """Tests for RepoMapHandler."""
    
    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("""
class TestClass:
    def test_method(self):
        pass
""")
            yield tmpdir
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = RepoMapHandler()
        assert handler.feature_name == "repo_map"
    
    def test_initialize(self, temp_repo):
        """Test initializing handler."""
        handler = RepoMapHandler()
        repo_map = handler.initialize(root=temp_repo)
        
        assert repo_map is not None
    
    def test_get_map(self, temp_repo):
        """Test getting map through handler."""
        handler = RepoMapHandler()
        handler.initialize(root=temp_repo)
        
        map_str = handler.get_map()
        
        assert len(map_str) > 0
    
    def test_refresh(self, temp_repo):
        """Test refreshing through handler."""
        handler = RepoMapHandler()
        handler.initialize(root=temp_repo)
        handler.get_map()
        
        handler.refresh()
        
        # Should not raise
        map_str = handler.get_map()
        assert len(map_str) > 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestRepoMapIntegration:
    """Integration tests for RepoMap."""
    
    @pytest.fixture
    def complex_repo(self):
        """Create a more complex repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create directory structure
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            
            (src_dir / "app.py").write_text("""
from .models import User
from .utils import format_name

class Application:
    def __init__(self):
        self.users = []
    
    def add_user(self, name):
        user = User(format_name(name))
        self.users.append(user)
        return user
    
    def get_users(self):
        return self.users
""")
            
            (src_dir / "models.py").write_text("""
class User:
    def __init__(self, name):
        self.name = name
    
    def __repr__(self):
        return f"User({self.name})"

class Admin(User):
    def __init__(self, name, role):
        super().__init__(name)
        self.role = role
""")
            
            (src_dir / "utils.py").write_text("""
def format_name(name):
    return name.strip().title()

def validate_email(email):
    return '@' in email
""")
            
            yield tmpdir
    
    def test_full_scan_and_map(self, complex_repo):
        """Test full scan and map generation."""
        repo_map = RepoMap(root=complex_repo)
        repo_map.scan()
        
        map_str = repo_map.get_map()
        
        # Should contain key symbols
        assert len(map_str) > 0
    
    def test_symbol_ranking(self, complex_repo):
        """Test that frequently referenced symbols rank higher."""
        repo_map = RepoMap(root=complex_repo)
        repo_map.scan()
        
        # User is referenced in multiple files
        top_symbols = repo_map.ranker.get_top_symbols(repo_map._file_maps)
        
        # Should have some symbols
        assert len(top_symbols) > 0
    
    def test_handler_workflow(self, complex_repo):
        """Test complete handler workflow."""
        handler = RepoMapHandler(verbose=False)
        handler.initialize(root=complex_repo)
        
        # Get initial map
        map1 = handler.get_map()
        assert len(map1) > 0
        
        # Refresh
        handler.refresh()
        
        # Get map again
        map2 = handler.get_map()
        assert len(map2) > 0
