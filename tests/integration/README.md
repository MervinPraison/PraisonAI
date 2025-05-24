# Integration Tests

This directory contains integration tests for PraisonAI that verify functionality across different frameworks and external dependencies.

## Test Structure

```
tests/integration/
├── README.md                    # This file
├── __init__.py                  # Package initialization
├── autogen/                     # AutoGen framework tests
│   ├── __init__.py
│   └── test_autogen_basic.py    # Basic AutoGen integration tests
├── crewai/                      # CrewAI framework tests  
│   ├── __init__.py
│   └── test_crewai_basic.py     # Basic CrewAI integration tests
├── test_base_url_api_base_fix.py # API base URL integration tests
├── test_mcp_integration.py      # Model Context Protocol tests
└── test_rag_integration.py      # RAG (Retrieval Augmented Generation) tests
```

## Framework Integration Tests

### AutoGen Integration Tests
Located in `autogen/test_autogen_basic.py`

**Test Coverage:**
- ✅ AutoGen import verification
- ✅ Basic agent creation through PraisonAI
- ✅ Conversation flow testing
- ✅ Configuration validation

**Example AutoGen Test:**
```python
def test_basic_autogen_agent_creation(self, mock_completion, mock_autogen_completion):
    """Test creating basic AutoGen agents through PraisonAI"""
    yaml_content = """
framework: autogen
topic: Test AutoGen Integration
roles:
  - name: Assistant
    goal: Help with test tasks
    backstory: I am a helpful assistant for testing
    tasks:
      - description: Complete a simple test task
        expected_output: Task completion confirmation
"""
```

### CrewAI Integration Tests
Located in `crewai/test_crewai_basic.py`

**Test Coverage:**
- ✅ CrewAI import verification
- ✅ Basic crew creation through PraisonAI
- ✅ Multi-agent workflow testing
- ✅ Agent collaboration verification
- ✅ Configuration validation

**Example CrewAI Test:**
```python
def test_crewai_agent_collaboration(self, mock_completion, mock_crewai_completion):
    """Test CrewAI agents working together in a crew"""
    yaml_content = """
framework: crewai
topic: Content Creation Pipeline
roles:
  - name: Content_Researcher  
    goal: Research topics for content creation
    backstory: Expert content researcher with SEO knowledge
    tasks:
      - description: Research trending topics in AI technology
        expected_output: List of trending AI topics with analysis
"""
```

## Running Integration Tests

### Using the Test Runner

**Run all integration tests:**
```bash
python tests/test_runner.py --pattern integration
```

**Run AutoGen tests only:**
```bash
python tests/test_runner.py --pattern autogen
```

**Run CrewAI tests only:**
```bash
python tests/test_runner.py --pattern crewai
```

**Run both framework tests:**
```bash
python tests/test_runner.py --pattern frameworks
```

**Run with verbose output:**
```bash
python tests/test_runner.py --pattern autogen --verbose
```

**Run with coverage reporting:**
```bash
python tests/test_runner.py --pattern integration --coverage
```

### Using pytest directly

**Run all integration tests:**
```bash
python -m pytest tests/integration/ -v
```

**Run AutoGen tests:**
```bash
python -m pytest tests/integration/autogen/ -v
```

**Run CrewAI tests:**
```bash
python -m pytest tests/integration/crewai/ -v
```

**Run specific test:**
```bash
python -m pytest tests/integration/autogen/test_autogen_basic.py::TestAutoGenIntegration::test_autogen_import -v
```

## Test Categories

### Framework Integration Tests
- **AutoGen**: Tests PraisonAI integration with Microsoft AutoGen framework
- **CrewAI**: Tests PraisonAI integration with CrewAI framework

### Feature Integration Tests
- **RAG**: Tests Retrieval Augmented Generation functionality
- **MCP**: Tests Model Context Protocol integration
- **Base URL/API**: Tests API base configuration and URL handling

## Test Dependencies

### Required for AutoGen Tests:
```bash
pip install pyautogen
```

### Required for CrewAI Tests:
```bash
pip install crewai
```

### Required for all integration tests:
```bash
pip install pytest pytest-asyncio
```

## Mock Strategy

All integration tests use comprehensive mocking to avoid:
- ❌ Real API calls (expensive and unreliable)
- ❌ Network dependencies 
- ❌ Rate limiting issues
- ❌ Environment-specific failures

**Mocking Pattern:**
```python
@patch('litellm.completion')
def test_framework_integration(self, mock_completion, mock_framework_completion):
    mock_completion.return_value = mock_framework_completion
    # Test logic here
```

## Expected Test Outcomes

### ✅ Success Scenarios
- Framework import successful
- Agent creation without errors
- Configuration validation passes
- Workflow initialization succeeds

### ⚠️ Skip Scenarios  
- Framework not installed → Test skipped with appropriate message
- Dependencies missing → Test skipped gracefully

### ❌ Failure Scenarios
- Configuration validation fails
- Agent creation errors
- Workflow initialization fails

## Adding New Framework Tests

To add tests for a new framework (e.g., `langchain`):

1. **Create directory:**
   ```bash
   mkdir tests/integration/langchain
   ```

2. **Create `__init__.py`:**
   ```python
   # LangChain Integration Tests
   ```

3. **Create test file:**
   ```python
   # tests/integration/langchain/test_langchain_basic.py
   class TestLangChainIntegration:
       @pytest.mark.integration
       def test_langchain_import(self):
           try:
               import langchain
               assert langchain is not None
           except ImportError:
               pytest.skip("LangChain not installed")
   ```

4. **Update test runner:**
   Add `"langchain"` to choices in `tests/test_runner.py`

## Best Practices

### Test Isolation
- ✅ Each test cleans up temporary files
- ✅ Tests don't depend on each other
- ✅ Mock external dependencies

### Performance  
- ✅ Fast execution (< 5 seconds per test)
- ✅ No real API calls
- ✅ Minimal file I/O

### Reliability
- ✅ Deterministic outcomes
- ✅ Clear error messages
- ✅ Graceful handling of missing dependencies

### Documentation
- ✅ Clear test names and docstrings
- ✅ Example configurations in tests
- ✅ Coverage of key use cases

## Troubleshooting

### Common Issues

**Import Errors:**
```
ImportError: No module named 'autogen'
```
**Solution:** Install the framework: `pip install pyautogen`

**Path Issues:**
```
ModuleNotFoundError: No module named 'praisonai'
```
**Solution:** Run tests from project root or add to PYTHONPATH

**Mock Issues:**
```
AttributeError: 'MagicMock' object has no attribute 'choices'
```
**Solution:** Verify mock structure matches expected API response

### Debug Mode

Enable detailed logging:
```bash
LOGLEVEL=DEBUG python tests/test_runner.py --pattern autogen --verbose
```

### Coverage Reports

Generate detailed coverage:
```bash
python tests/test_runner.py --pattern frameworks --coverage
```

This will show which integration test code paths are covered and highlight areas needing additional testing. 