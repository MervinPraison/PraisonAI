# AI Code Editor Smoke Test Verification Ledger

**Date**: January 2026  
**Status**: VERIFIED  

## CLI Contract Table

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `praisonai chat` | Terminal-native REPL | `-m`, `-w`, `-f`, `-c`, `-s`, `--no-acp`, `--no-lsp` |
| `praisonai code` | Terminal-native code assistant | `-m`, `-w`, `-f`, `-c`, `-s`, `--no-acp`, `--no-lsp` |
| `praisonai tui` | Full TUI interface | `-w`, `-s`, `-m`, `-d`, `--log-jsonl` |
| `praisonai ui chat` | Browser-based chat | `--port`, `--host`, `--public` |
| `praisonai ui code` | Browser-based code | `--port`, `--host`, `--public` |
| `praisonai session list` | List sessions | - |
| `praisonai session export` | Export session | `--output` |
| `praisonai session import` | Import session | - |

## Approval Automation Mechanism

- **Environment Variable**: `PRAISON_APPROVAL_MODE=auto`
- **Effect**: Auto-approves all tool executions for non-interactive automation
- **Files Modified**:
  - `praisonai/cli/main.py` - Added env var check in `_process_interactive_prompt` and `_start_execution_worker`
  - `praisonai/cli/features/interactive_runtime.py` - Modified `read_only` property to bypass when auto mode

## Scenario Table (10 Scenarios)

| # | Scenario Name | CLI Command | Acceptance Checks | Status |
|---|---------------|-------------|-------------------|--------|
| 1 | implement_celsius_to_fahrenheit | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | function_exists, has_formula, tests_pass | PASS |
| 2 | fix_divide_by_zero | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | has_error_message, tests_pass | PASS |
| 3 | implement_mode_function | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | tests_pass | PASS |
| 4 | fix_mean_empty_list | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | has_error_message, tests_pass | PASS |
| 5 | add_cli_version_command | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | has_version_command, version_works | PASS |
| 6 | fix_lint_errors | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | ruff_clean | PASS |
| 7 | implement_fahrenheit_to_celsius | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | function_exists, tests_pass | PASS |
| 8 | fix_median_empty_list | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | has_error_message, tests_pass | PASS |
| 9 | add_type_hints_calculator | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | has_return_type, has_param_types | PASS |
| 10 | make_all_tests_pass | `praisonai code -m gpt-4o-mini -w <workspace> "<prompt>"` | all_tests_pass | PASS |

## Files Modified

### CLI Fixes
- `praisonai/cli/main.py` - Added PRAISON_APPROVAL_MODE=auto support, fixed import error handling
- `praisonai/cli/features/interactive_runtime.py` - Modified read_only property for auto mode
- `praisonai/api.py` - Fixed circular import

### Test Infrastructure
- `tests/live/runner.py` - CLI-first runner using `python -m praisonai code`
- `tests/live/scenarios/__init__.py` - 10 scenario definitions with acceptance checks
- `tests/live/test_ai_code_editor_smoke.py` - Pytest test suite

### Fixture
- `tests/fixtures/ai_code_editor_fixture/` - Single fixture template with intentional bugs

### Documentation
- `PraisonAIDocs/docs/cli/realworld-examples.mdx` - Updated with CLI contract and scenarios

## Environment Guards

```bash
# Required for live tests
PRAISONAI_LIVE_SMOKE=1
OPENAI_API_KEY=<your-key>

# Optional
PRAISONAI_LIVE_MODEL=gpt-4o-mini  # Default model
PRAISON_APPROVAL_MODE=auto        # Auto-approve tools
```

## Run Commands

```bash
# Run all live smoke tests
PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py -v

# Run single scenario
PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py::TestIndividualScenarios::test_scenario_2_fix_divide_bug -v

# Run fixture verification only
PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py::TestAICodeEditorSmoke::test_fixture_has_failing_tests -v
```

## Deprecated Flags (Removed)

- `--interactive` / `-i` - Use `praisonai chat` instead
- `--chat-mode` / `--chat` - Use `praisonai chat` instead
- `tui launch` - Use `praisonai tui` directly

## Missing = 0

All 10 scenarios defined and verified with CLI-first approach.
