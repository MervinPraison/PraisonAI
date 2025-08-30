# AutoGen v0.4 Test Suite

This directory contains comprehensive tests for the AutoGen v0.4 integration with PraisonAI. The tests ensure that the new AutoGen v0.4 functionality works correctly while maintaining full backward compatibility with AutoGen v0.2.

## Test Files Overview

### 1. `test_autogen_v4_integration.py`
**Primary Integration Tests**
- Tests the core AutoGen v0.4 async execution functionality
- Verifies proper integration with new v0.4 components:
  - `AutoGenV4AssistantAgent`
  - `OpenAIChatCompletionClient`
  - `RoundRobinGroupChat`
  - `TextMentionTermination` & `MaxMessageTermination`
- Tests tool integration and agent creation patterns
- Validates error handling and resource management

### 2. `test_autogen_version_selection.py`
**Version Selection Logic Tests**
- Tests the `AUTOGEN_VERSION` environment variable behavior
- Verifies automatic version preference (v0.4 preferred over v0.2)
- Tests explicit version selection (`v0.2`, `v0.4`, `auto`)
- Validates fallback logic when versions are unavailable
- Tests case-insensitive version string handling
- Verifies AgentOps tagging for different versions

### 3. `test_autogen_v4_utils.py`
**Utility Functions Tests**
- Tests `sanitize_agent_name_for_autogen_v4()` function
- Validates topic formatting in agent names and descriptions
- Tests tool filtering for v0.4 (callable `run` methods)
- Verifies task description construction
- Tests result message extraction logic
- Validates model configuration defaults

### 4. `test_autogen_backward_compatibility.py`
**Backward Compatibility Tests**
- Ensures existing v0.2 code continues to work unchanged
- Tests that the same configuration works with both versions
- Verifies no breaking changes in the API
- Tests tool compatibility across versions
- Validates config structure compatibility
- Tests smooth migration path from v0.2 to v0.4

### 5. `test_autogen_v4_edge_cases.py`
**Edge Cases and Error Scenarios**
- Tests empty configurations and missing fields
- Validates handling of invalid tool references
- Tests asyncio runtime error handling
- Verifies model client and agent creation failures
- Tests extreme agent names and Unicode characters
- Validates memory-intensive operations
- Tests malformed result message handling

## Running the Tests

### Run All AutoGen v0.4 Tests
```bash
python tests/run_autogen_v4_tests.py
```

### Run Specific Test Categories
```bash
# Integration tests
python tests/run_autogen_v4_tests.py integration

# Version selection tests
python tests/run_autogen_v4_tests.py version

# Utility function tests
python tests/run_autogen_v4_tests.py utils

# Backward compatibility tests
python tests/run_autogen_v4_tests.py compatibility

# Edge case tests
python tests/run_autogen_v4_tests.py edge_cases
```

### Run Individual Test Files
```bash
# Run specific test file
pytest tests/unit/test_autogen_v4_integration.py -v

# Run specific test method
pytest tests/unit/test_autogen_v4_integration.py::TestAutoGenV4Integration::test_version_detection_auto_prefers_v4 -v
```

## Test Coverage

The test suite covers:

### ✅ **Core Functionality**
- [x] AutoGen v0.4 async execution pattern
- [x] Agent creation with v0.4 components
- [x] Tool integration (callable `run` methods)
- [x] Group chat creation and execution
- [x] Termination conditions (text + max messages)
- [x] Model client configuration and resource management

### ✅ **Version Management**
- [x] Environment variable handling (`AUTOGEN_VERSION`)
- [x] Automatic version detection and preference
- [x] Explicit version selection
- [x] Fallback logic for missing versions
- [x] Import error handling
- [x] AgentOps integration and tagging

### ✅ **Backward Compatibility**
- [x] Existing v0.2 code continues working
- [x] Same configuration works with both versions
- [x] No breaking API changes
- [x] Tool compatibility across versions
- [x] Smooth migration path

### ✅ **Error Handling**
- [x] AsyncIO runtime errors
- [x] Model client creation failures
- [x] Agent creation failures
- [x] Group chat execution failures
- [x] Resource cleanup on errors
- [x] Malformed configuration handling

### ✅ **Edge Cases**
- [x] Empty configurations
- [x] Missing configuration fields
- [x] Invalid tool references
- [x] Extreme agent names
- [x] Unicode character handling
- [x] Memory-intensive operations
- [x] Large configuration files

## Mock Strategy

The tests use comprehensive mocking to:
- **Mock AutoGen Dependencies**: Tests work regardless of which AutoGen versions are installed
- **Mock Async Components**: Proper async/await testing with `AsyncMock`
- **Mock External APIs**: No real API calls during testing
- **Mock File System**: No real file I/O during tests
- **Isolated Testing**: Each test is independent and doesn't affect others

## Test Environment

The tests are designed to:
- Run in CI/CD environments without AutoGen installed
- Work with or without actual AutoGen v0.2/v0.4 dependencies
- Provide comprehensive coverage of all code paths
- Execute quickly with minimal external dependencies
- Generate clear, actionable error messages

## Integration with Existing Test Suite

These tests integrate seamlessly with the existing PraisonAI test suite:
- Follow the same testing patterns and conventions
- Use the same fixtures and utilities from `conftest.py`
- Compatible with the existing test runner infrastructure
- Maintain consistent error handling and logging

## Dependencies

The test suite requires:
- `pytest` (testing framework)
- `unittest.mock` (mocking capabilities)
- Standard Python library modules

No actual AutoGen dependencies are required to run the tests.

## Contributing

When adding new AutoGen v0.4 functionality:
1. Add corresponding tests to the appropriate test file
2. Ensure both happy path and error scenarios are tested
3. Verify backward compatibility is maintained
4. Update this README if new test categories are added
5. Run the full test suite to ensure no regressions

## Test Results

The test suite provides:
- **Comprehensive Coverage**: All AutoGen v0.4 functionality is tested
- **Clear Reporting**: Detailed test results and failure information
- **Fast Execution**: Tests complete in under 1 minute
- **Reliable Results**: Tests are deterministic and reproducible
- **Easy Debugging**: Clear error messages and test isolation