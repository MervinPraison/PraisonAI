# Live AI Code Editor Smoke Tests

This directory contains end-to-end smoke tests for the PraisonAI AI code editor functionality. These tests verify that PraisonAI behaves as a real AI code editor by editing files on disk, running terminal commands, observing failures, and converging to green tests.

## Setup Requirements

### Required Environment Variables
```bash
PRAISONAI_LIVE_SMOKE=1      # Enable live smoke tests  
OPENAI_API_KEY=<your-key>   # Required for LLM calls
```

### Optional Environment Variables
```bash
PRAISONAI_LIVE_MODEL=gpt-4o-mini  # Override default model
PRAISON_APPROVAL_MODE=auto        # Auto-approve tools (required for automation)
```

### Working Directory
The current working directory must be `src/praisonai` when running tests to ensure proper path resolution.

```bash
cd src/praisonai
PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py -v
```

## Windows Compatibility (Issue #1839)

This test harness has been updated to fix Windows compatibility issues:

### 1. PYTHONPATH Handling
- **Issue**: Used Unix `:` separator instead of `os.pathsep`
- **Fix**: `build_cli_env()` now uses `os.pathsep.join(paths)` for cross-platform compatibility

### 2. UTF-8 Encoding
- **Issue**: subprocess calls without explicit encoding caused UnicodeDecodeError on Windows
- **Fix**: All subprocess calls now include `encoding="utf-8", errors="replace"`
- **Environment**: Added `PYTHONIOENCODING=utf-8` for subprocess I/O

### 3. Windows Automation
- **Issue**: `praisonai code` hangs in non-interactive Windows runs
- **Fix**: Automatically adds `--no-acp` flag when `os.name == "nt"`

### 4. Pytest Environment Isolation  
- **Issue**: Nested pytest inherited dev `PYTHONPATH` from `build_cli_env()`
- **Fix**: New `build_isolated_pytest_env()` function strips `PYTHONPATH` for acceptance checks

### 5. Precise Test Selectors
- **Issue**: `-k celsius` matched both `test_celsius_to_fahrenheit` and `test_fahrenheit_to_celsius`  
- **Fix**: Use specific node IDs like `tests/test_converter.py::test_celsius_to_fahrenheit`

### 6. Missing Fixture
- **Issue**: `ai_code_editor_fixture` directory was missing from releases
- **Fix**: Complete fixture created with mathlib project and intentional bugs

## Test Structure

### Runner (`runner.py`)
- CLI-first test execution using `python -m praisonai code`
- Cross-platform environment setup
- File snapshot and diff utilities
- Timeout and error handling

### Scenarios (`scenarios/__init__.py`)
- 10+ comprehensive scenarios covering AI code editor capabilities
- Acceptance checks for function existence, test passing, linting
- Node-ID based test selectors for precision

### Test Suite (`test_ai_code_editor_smoke.py`)
- Pytest test class with parametrized scenarios
- Fixture validation
- Individual scenario debugging

### Fixture (`../fixtures/ai_code_editor_fixture/`)
- Complete Python project with intentional bugs
- Calculator, converter, stats modules
- Comprehensive test suite that initially fails
- CLI interface to test

## Running Tests

### All Scenarios
```bash
cd src/praisonai
PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py -v
```

### Single Scenario
```bash
cd src/praisonai  
PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py::TestIndividualScenarios::test_scenario_1_implement_converter -v
```

### Fixture Validation Only
```bash
cd src/praisonai
PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py::TestAICodeEditorSmoke::test_fixture_has_failing_tests -v
```

## Cross-Platform Notes

### Windows
- Requires `--no-acp` for automation (automatically added)
- Uses `;` for PYTHONPATH separator
- Requires explicit UTF-8 encoding for subprocess I/O

### Linux/macOS  
- Uses `:` for PYTHONPATH separator
- Default system encoding usually sufficient
- No special automation flags needed

## Troubleshooting

### Tests Skip or Don't Run
- Ensure `PRAISONAI_LIVE_SMOKE=1` is set
- Ensure `OPENAI_API_KEY` is provided
- Run from `src/praisonai` directory

### Windows UnicodeDecodeError
- Ensure `PYTHONIOENCODING=utf-8` is set (should be automatic)
- Check that all subprocess calls include UTF-8 encoding

### Pytest Hangs or Fails Unexpectedly
- Ensure isolated pytest environment is used  
- Check that `--no-acp` is added for Windows automation

### Import Errors
- Verify PYTHONPATH includes both `praisonai` and `praisonai-agents`
- Check that paths use correct separator for platform

## Architecture

These tests follow a **CLI-first approach**: all scenarios execute via `praisonai code` CLI commands, not direct Python Agent API calls. This ensures we're testing the actual CLI interface that users interact with.

The harness is designed to be:
- **Cross-platform**: Works on Windows, Linux, and macOS
- **Isolated**: Each test gets a fresh fixture copy
- **Comprehensive**: Covers implementation, debugging, refactoring, and tooling
- **Realistic**: Uses actual LLM calls in real scenarios