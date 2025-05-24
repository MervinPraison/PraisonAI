# Framework Integration Tests - Workflow Integration

This document summarizes how the AutoGen and CrewAI integration tests have been integrated into the GitHub workflows.

## ✅ Workflows Updated

### 1. **Core Tests** (`.github/workflows/test-core.yml`)
**Added:** Explicit framework testing steps
- 🤖 **AutoGen Framework Tests**: Dedicated step with emoji indicator
- ⛵ **CrewAI Framework Tests**: Dedicated step with emoji indicator
- Both steps use `continue-on-error: true` to prevent blocking main test flow

**Triggers:** 
- Push to `main`/`develop` branches
- Pull requests to `main`/`develop` branches

### 2. **Comprehensive Test Suite** (`.github/workflows/test-comprehensive.yml`)
**Added:** Framework-specific test options
- New input choices: `frameworks`, `autogen`, `crewai`
- Test execution logic for each framework pattern
- Updated test report to include framework integration results

**Triggers:**
- Manual workflow dispatch with framework selection
- Weekly scheduled runs (Sundays at 3 AM UTC)
- Release events

### 3. **NEW: Framework Integration Tests** (`.github/workflows/test-frameworks.yml`)
**Created:** Dedicated framework testing workflow
- **Matrix Strategy**: Tests both Python 3.9 and 3.11 with both frameworks
- **Individual Framework Testing**: Separate jobs for AutoGen and CrewAI
- **Comprehensive Reporting**: Detailed test reports with coverage
- **Summary Generation**: Aggregated results across all combinations

**Triggers:**
- **Daily Scheduled**: 6 AM UTC every day
- **Manual Dispatch**: With framework selection (all/autogen/crewai)
- **Path-based**: Triggers when framework test files change

## 📊 Test Coverage in Workflows

### Core Tests Workflow
```yaml
- name: Run AutoGen Framework Tests
  run: |
    echo "🤖 Testing AutoGen Framework Integration..."
    python tests/test_runner.py --pattern autogen --verbose
  continue-on-error: true

- name: Run CrewAI Framework Tests  
  run: |
    echo "⛵ Testing CrewAI Framework Integration..."
    python tests/test_runner.py --pattern crewai --verbose
  continue-on-error: true
```

### Comprehensive Tests Workflow
```yaml
case $TEST_TYPE in
  "frameworks")
    python tests/test_runner.py --pattern frameworks
    ;;
  "autogen")
    python tests/test_runner.py --pattern autogen
    ;;
  "crewai")
    python tests/test_runner.py --pattern crewai
    ;;
esac
```

### Framework-Specific Workflow
```yaml
strategy:
  matrix:
    python-version: [3.9, 3.11]
    framework: [autogen, crewai]

- name: Test ${{ matrix.framework }} Framework
  run: |
    python tests/test_runner.py --pattern ${{ matrix.framework }} --verbose --coverage
```

## 🚀 How to Trigger Framework Tests

### 1. **Automatic Triggers**
- **Every Push/PR**: Core tests include framework tests automatically
- **Daily at 6 AM UTC**: Dedicated framework workflow runs
- **Weekly on Sundays**: Comprehensive tests can include framework tests

### 2. **Manual Triggers**

**Run comprehensive tests with frameworks:**
```bash
# In GitHub UI: Actions → Comprehensive Test Suite → Run workflow
# Select: "frameworks" from dropdown
```

**Run dedicated framework tests:**
```bash
# In GitHub UI: Actions → Framework Integration Tests → Run workflow  
# Select: "all", "autogen", or "crewai" from dropdown
```

### 3. **Local Testing**
All framework tests can be run locally using the test runner:

```bash
# Run both frameworks
python tests/test_runner.py --pattern frameworks

# Run AutoGen only
python tests/test_runner.py --pattern autogen --verbose

# Run CrewAI only  
python tests/test_runner.py --pattern crewai --verbose

# Run with coverage
python tests/test_runner.py --pattern frameworks --coverage
```

## 📋 Test Artifacts Generated

### Framework Test Reports
- `autogen_report.md` - AutoGen test results and coverage
- `crewai_report.md` - CrewAI test results and coverage
- `framework_summary.md` - Aggregated results across all frameworks

### Coverage Reports
- `htmlcov/` - HTML coverage reports
- `coverage.xml` - XML coverage data
- `.coverage` - Coverage database

### Retention Policies
- **Framework Reports**: 14 days
- **Comprehensive Reports**: 30 days
- **Summary Reports**: 30 days

## 🔍 Test Discovery

The workflows automatically discover and run all tests in:
- `tests/integration/autogen/` - AutoGen framework tests
- `tests/integration/crewai/` - CrewAI framework tests

## ⚙️ Configuration

### Dependencies Installed
All workflows install both framework dependencies:
```yaml
uv pip install --system ."[crewai,autogen]"
```

### Environment Variables
Standard PraisonAI test environment:
- `OPENAI_API_KEY` - From GitHub secrets
- `OPENAI_API_BASE` - From GitHub secrets  
- `OPENAI_MODEL_NAME` - From GitHub secrets
- `PYTHONPATH` - Set to include praisonai-agents source

### Error Handling
- **Core Tests**: Framework tests use `continue-on-error: true`
- **Comprehensive Tests**: Framework tests run as part of main flow
- **Dedicated Framework Tests**: Framework tests use `continue-on-error: false`

## 🎯 Benefits

1. **Visibility**: Framework tests are clearly visible in all workflows
2. **Flexibility**: Can run individual frameworks or combined
3. **Scheduling**: Automated daily testing ensures ongoing compatibility
4. **Reporting**: Detailed reports help identify framework-specific issues
5. **Matrix Testing**: Validates compatibility across Python versions
6. **Isolation**: Dedicated workflow prevents framework issues from blocking core tests

## 📈 Next Steps

Future enhancements could include:
- Performance benchmarking for framework integrations
- Integration with external framework test suites
- Notification systems for framework test failures
- Framework version compatibility testing 