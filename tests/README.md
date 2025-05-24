# PraisonAI Agents - Comprehensive Testing Suite

This directory contains a comprehensive testing suite for PraisonAI Agents, organized into different categories to ensure thorough coverage of all functionality.

## 📁 Test Structure

```
tests/
├── conftest.py                    # Pytest configuration and fixtures
├── test_runner.py                 # Comprehensive test runner script
├── README.md                      # This documentation
├── unit/                          # Unit tests for core functionality
│   ├── __init__.py
│   ├── test_core_agents.py        # Core agent, task, and LLM tests
│   ├── test_async_agents.py       # Async functionality tests
│   ├── test_tools_and_ui.py       # Tools and UI integration tests
│   └── agent/                     # Legacy agent tests
│       ├── test_mini_agents_fix.py
│       ├── test_mini_agents_sequential.py
│       └── test_type_casting.py
├── integration/                   # Integration tests for complex features
│   ├── __init__.py
│   ├── test_base_url_api_base_fix.py  # Base URL mapping tests
│   ├── test_mcp_integration.py        # MCP protocol tests
│   └── test_rag_integration.py        # RAG functionality tests
├── test.py                        # Legacy example tests
├── basic_example.py              # Basic agent example
├── advanced_example.py           # Advanced agent example
├── auto_example.py               # Auto agent example
└── agents.yaml                   # Sample agent configuration
```

## 🧪 Test Categories

### 1. Unit Tests (`tests/unit/`)
Fast, isolated tests for core functionality:

- **Core Agents** (`test_core_agents.py`)
  - Agent creation and configuration
  - Task management and execution
  - LLM integration and chat functionality
  - Multi-agent orchestration

- **Async Functionality** (`test_async_agents.py`)
  - Async agents and tasks
  - Async tool integration
  - Mixed sync/async workflows
  - Async memory operations

- **Tools & UI** (`test_tools_and_ui.py`)
  - Custom tool creation and integration
  - Multi-modal tools (image, audio, document)
  - UI framework configurations (Gradio, Streamlit, Chainlit)
  - API endpoint simulation

### 2. Integration Tests (`tests/integration/`)
Complex tests for integrated systems:

- **MCP Integration** (`test_mcp_integration.py`)
  - Model Context Protocol server connections
  - Tool execution via MCP
  - Multiple server management
  - Error handling and recovery

- **RAG Integration** (`test_rag_integration.py`)
  - Knowledge base creation and indexing
  - Vector store operations (ChromaDB, Pinecone, Weaviate)
  - Document processing and retrieval
  - Memory persistence and updates

- **Base URL Mapping** (`test_base_url_api_base_fix.py`)
  - LiteLLM compatibility fixes
  - OpenAI-compatible endpoint support
  - KoboldCPP integration

## 🚀 Running Tests

### Quick Start
```bash
# Run all tests with the comprehensive test runner
python tests/test_runner.py

# Run specific test categories
python tests/test_runner.py --unit
python tests/test_runner.py --integration
python tests/test_runner.py --fast

# Run tests matching a pattern
python tests/test_runner.py --pattern "agent"
python tests/test_runner.py --markers "not slow"
```

### Using Pytest Directly
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test files
pytest tests/unit/test_core_agents.py -v
pytest tests/integration/test_mcp_integration.py -v

# Run with coverage
pytest tests/ --cov=praisonaiagents --cov-report=html

# Run async tests only
pytest tests/ -k "async" -v

# Run with specific markers
pytest tests/ -m "not slow" -v
```

### GitHub Actions
The comprehensive test suite runs automatically on push/pull request with:
- Multiple Python versions (3.9, 3.10, 3.11)
- All test categories
- Coverage reporting
- Performance benchmarking
- Example script validation

## 🔧 Key Features Tested

### Core Functionality
- ✅ Agent creation and configuration
- ✅ Task management and execution
- ✅ LLM integrations (OpenAI, Anthropic, Gemini, Ollama, DeepSeek)
- ✅ Multi-agent workflows (sequential, hierarchical, workflow)

### Advanced Features
- ✅ **Async Operations**: Async agents, tasks, and tools
- ✅ **RAG (Retrieval Augmented Generation)**: Knowledge bases, vector stores
- ✅ **MCP (Model Context Protocol)**: Server connections and tool execution
- ✅ **Memory Systems**: Persistent memory and knowledge updates
- ✅ **Multi-modal Tools**: Image, audio, and document processing

### Integrations
- ✅ **Search Tools**: DuckDuckGo, web scraping
- ✅ **UI Frameworks**: Gradio, Streamlit, Chainlit
- ✅ **API Endpoints**: REST API simulation and testing
- ✅ **Vector Stores**: ChromaDB, Pinecone, Weaviate support

### Error Handling & Performance
- ✅ **Error Recovery**: Tool failures, connection errors
- ✅ **Performance**: Agent creation, import speed
- ✅ **Compatibility**: Base URL mapping, provider switching

## 📊 Test Configuration

### Fixtures (`conftest.py`)
Common test fixtures available across all tests:
- `mock_llm_response`: Mock LLM API responses
- `sample_agent_config`: Standard agent configuration
- `sample_task_config`: Standard task configuration
- `mock_vector_store`: Mock vector store operations
- `mock_duckduckgo`: Mock search functionality
- `temp_directory`: Temporary file system for tests

### Environment Variables
Tests automatically set up mock environment variables:
- `OPENAI_API_KEY=test-key`
- `ANTHROPIC_API_KEY=test-key`
- `GOOGLE_API_KEY=test-key`

### Markers
Custom pytest markers for test organization:
- `@pytest.mark.asyncio`: Async tests
- `@pytest.mark.slow`: Long-running tests
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.unit`: Unit tests

## 🔍 Adding New Tests

### 1. Unit Tests
Add to `tests/unit/` for isolated functionality:
```python
def test_new_feature(sample_agent_config):
    """Test new feature functionality."""
    agent = Agent(**sample_agent_config)
    result = agent.new_feature()
    assert result is not None
```

### 2. Integration Tests
Add to `tests/integration/` for complex workflows:
```python
@pytest.mark.asyncio
async def test_complex_workflow(mock_vector_store):
    """Test complex multi-component workflow."""
    # Setup multiple components
    # Test interaction between them
    assert workflow_result.success is True
```

### 3. Async Tests
Use the `@pytest.mark.asyncio` decorator:
```python
@pytest.mark.asyncio
async def test_async_functionality():
    """Test async operations."""
    result = await async_function()
    assert result is not None
```

## 📈 Coverage Goals

- **Unit Tests**: 90%+ coverage of core functionality
- **Integration Tests**: All major feature combinations
- **Error Handling**: All exception paths tested
- **Performance**: Benchmarks for critical operations

## 🛠️ Dependencies

### Core Testing
- `pytest`: Test framework
- `pytest-asyncio`: Async test support
- `pytest-cov`: Coverage reporting

### Mocking
- `unittest.mock`: Built-in mocking
- Mock external APIs and services

### Test Data
- Temporary directories for file operations
- Mock configurations for all integrations
- Sample data for various scenarios

## 📝 Best Practices

1. **Isolation**: Each test should be independent
2. **Mocking**: Mock external dependencies and APIs
3. **Naming**: Clear, descriptive test names
4. **Documentation**: Document complex test scenarios
5. **Performance**: Keep unit tests fast (<1s each)
6. **Coverage**: Aim for high coverage of critical paths
7. **Maintainability**: Regular test maintenance and updates

## 🔄 Continuous Integration

The test suite integrates with GitHub Actions for:
- Automated testing on all PRs
- Multi-Python version compatibility
- Performance regression detection
- Test result artifacts and reporting

## 📞 Support

For questions about testing:
1. Check this README for guidance
2. Review existing tests for patterns
3. Check the `conftest.py` for available fixtures
4. Run `python tests/test_runner.py --help` for options 