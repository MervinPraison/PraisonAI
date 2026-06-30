# Real End-to-End Tests

⚠️ **WARNING: These tests make real API calls and may incur costs!**

## 🎯 Purpose

This directory contains **real end-to-end tests** that make actual API calls to test PraisonAI framework integrations. These are fundamentally different from the mock tests in `tests/integration/`.

## 🆚 Mock vs Real Tests

| Aspect | Mock Tests (`tests/integration/`) | Real Tests (`tests/e2e/`) |
|--------|-----------------------------------|---------------------------|
| **API Calls** | ❌ Mocked with `@patch('litellm.completion')` | ✅ Real LLM API calls |
| **Cost** | 🆓 Free to run | 💰 Consumes API credits |
| **Speed** | ⚡ Fast (~5 seconds) | 🐌 Slower (~30+ seconds) |
| **Reliability** | ✅ Always consistent | ⚠️ Depends on API availability |
| **Purpose** | Test integration logic | Test actual functionality |
| **CI/CD** | ✅ Run on every commit | ⚙️ Manual/scheduled only |

## 📂 Structure

```
tests/e2e/
├── autogen/
│   └── test_autogen_real.py    # Real AutoGen tests
├── crewai/
│   └── test_crewai_real.py     # Real CrewAI tests
├── langgraph_e2e/
│   └── test_langgraph_real.py  # Real LangGraph tests
├── openai_agents_e2e/
│   └── test_openai_agents_real.py  # Real OpenAI Agents SDK tests
├── agno_e2e/
│   └── test_agno_real.py           # Real Agno tests
├── google_adk_e2e/
│   └── test_google_adk_real.py     # Real Google ADK tests
├── README.md                   # This file
└── __init__.py
```

## 🚀 Running Real Tests

### Prerequisites

1. **API Keys Required:**
   ```bash
   export OPENAI_API_KEY="your-actual-api-key"
   # Optional: Other provider keys
   export ANTHROPIC_API_KEY="your-key"
   ```

   ⚠️ **Important**: The tests were originally failing with "test-key" because `tests/conftest.py` was overriding all API keys for mock tests. This has been fixed to preserve real API keys for tests marked with `@pytest.mark.real`.

2. **Framework Dependencies:**
   ```bash
   pip install ".[crewai,autogen]"
   ```

3. **Understanding of Costs:**
   - Each test may make multiple API calls
   - Costs depend on your API provider and model
   - Tests are kept minimal to reduce costs

### Running Commands

**Run all real tests:**
```bash
python -m pytest tests/e2e/ -v -m real
```

**Run AutoGen real tests only:**
```bash
python -m pytest tests/e2e/autogen/ -v -m real
```

**Run CrewAI real tests only:**
```bash
python -m pytest tests/e2e/crewai/ -v -m real
```

**Run with full execution (actual praisonai.run()):**
```bash
# Enable full execution tests
export PRAISONAI_RUN_FULL_TESTS=true

# Run with real-time output to see actual execution
python -m pytest tests/e2e/autogen/ -v -m real -s
```

**Run OpenAI Agents real tests only:**
```bash
python -m pytest tests/e2e/openai_agents_e2e/ -v -m real
```

**Run Agno real tests only:**
```bash
python -m pytest tests/e2e/agno_e2e/ -v -m real
```

**Run Google ADK real tests only:**
```bash
PRAISONAI_LIVE_TESTS=1 PRAISONAI_TEST_PROVIDERS=all python -m pytest tests/e2e/google_adk_e2e/ -v -m real
```

**Skip real tests (default behavior without API keys):**
```bash
python -m pytest tests/e2e/ -v
# Will skip all tests marked with @pytest.mark.real if no API key
```

### Using Test Runner

**Setup-only real tests:**
```bash
python tests/test_runner.py --pattern real-autogen
```

**Full execution tests (with praisonai.run()):**
```bash
python tests/test_runner.py --pattern full-autogen
```

## 🧪 Test Categories

### AutoGen Real Tests
- **Environment Check**: Verify API keys and imports
- **Simple Conversation**: Basic agent interaction
- **Agent Creation**: Real agent setup without full execution

### CrewAI Real Tests  
- **Environment Check**: Verify API keys and imports
- **Simple Crew**: Basic crew setup
- **Multi-Agent Setup**: Multiple agents configuration

## 💡 Test Philosophy

### What We Test
- ✅ **Environment Setup**: API keys, imports, dependencies
- ✅ **Framework Integration**: PraisonAI + AutoGen/CrewAI
- ✅ **Agent Creation**: Real agent/crew instantiation
- ✅ **Configuration Loading**: YAML parsing and validation

### What We Don't Test (To Minimize Costs)
- ❌ **Full Conversations**: Would be expensive
- ❌ **Long Workflows**: Would consume many tokens
- ❌ **Performance Testing**: Would require many runs

### Cost Minimization Strategy
- **Minimal Configurations**: Simple agents and tasks
- **Setup-Only Tests**: Initialize but don't execute
- **Skip Markers**: Automatic skipping without API keys
- **Clear Warnings**: Users understand costs before running

## 🔧 Configuration

### API Key Requirements
Real tests require at least one of:
- `OPENAI_API_KEY` - For OpenAI models
- `ANTHROPIC_API_KEY` - For Claude models  
- `GOOGLE_API_KEY` - For Gemini models

### Test Markers
All real tests use `@pytest.mark.real`:
```python
@pytest.mark.real
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
def test_real_functionality(self):
    # Test code that makes real API calls
```

### Temporary Files
Tests create temporary YAML files and clean up automatically:
```python
with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
    f.write(yaml_content)
    test_file = f.name
try:
    # Test logic
finally:
    if os.path.exists(test_file):
        os.unlink(test_file)
```

## 🚨 Safety Features

### Automatic Skipping
Tests automatically skip if:
- No API keys are set
- Required frameworks not installed
- Network connectivity issues

### Error Handling
- Graceful failure with clear error messages
- Proper cleanup of temporary files
- No hanging connections or resources

### Cost Warnings
- Clear warnings in test names and docstrings
- Documentation emphasizes cost implications
- Tests kept minimal by design

## 🎯 When to Run Real Tests

### Good Times to Run:
- ✅ Before major releases
- ✅ When testing new framework integrations
- ✅ When debugging actual API issues
- ✅ Manual testing of critical functionality

### Avoid Running:
- ❌ On every commit (use mock tests instead)
- ❌ Without understanding costs
- ❌ In CI/CD for routine checks
- ❌ When debugging non-API related issues

## 🔮 Future Enhancements

### Planned Features:
- [ ] Integration with `test_runner.py`
- [ ] Cost estimation before running
- [ ] Different test "levels" (quick/full)
- [ ] Result caching to avoid repeated calls
- [ ] Performance benchmarking
- [ ] Integration with GitHub Actions (manual only)

### Additional Frameworks:
- [ ] LangChain real tests
- [ ] Custom framework tests
- [ ] Multi-framework comparison tests

## 📊 Comparison Summary

| Test Type | Mock Tests | Real Tests |
|-----------|------------|------------|
| **When to Use** | Development, CI/CD, routine testing | Pre-release, debugging, validation |
| **What They Test** | Integration logic, configuration | Actual functionality, API compatibility |
| **Cost** | Free | Paid (API usage) |
| **Speed** | Fast | Slow |
| **Reliability** | High | Depends on external services |
| **Frequency** | Every commit | Manual/scheduled |

Both test types are important and complementary - mock tests for development velocity, real tests for production confidence! 