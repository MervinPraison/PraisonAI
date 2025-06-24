# PraisonAI Testing Guide

This guide explains the complete testing structure for PraisonAI, including both mock and real tests.

## 📂 Testing Structure

```
tests/
├── unit/                     # Unit tests (fast, isolated)
├── integration/              # Mock integration tests (free)
│   ├── autogen/             # AutoGen mock tests
│   ├── crewai/              # CrewAI mock tests
│   └── README.md            # Mock test documentation
├── e2e/                     # Real end-to-end tests (costly!)
│   ├── autogen/             # AutoGen real tests
│   ├── crewai/              # CrewAI real tests
│   └── README.md            # Real test documentation
├── test_runner.py           # Universal test runner
└── TESTING_GUIDE.md         # This file
```

## 🎭 Mock vs Real Tests

| Test Type | Location | API Calls | Cost | Speed | When to Use |
|-----------|----------|-----------|------|-------|-------------|
| **Mock Tests** | `tests/integration/` | ❌ Mocked | 🆓 Free | ⚡ Fast | Development, CI/CD |
| **Real Tests** | `tests/e2e/` | ✅ Actual | 💰 Paid | 🐌 Slow | Pre-release, debugging |

## 🚀 Running Tests

### Using Test Runner (Recommended)

**Mock Tests (Free):**
```bash
# All mock integration tests
python tests/test_runner.py --pattern frameworks

# AutoGen mock tests only
python tests/test_runner.py --pattern autogen

# CrewAI mock tests only  
python tests/test_runner.py --pattern crewai
```

**Real Tests (Costly!):**
```bash
# All real tests (will prompt for confirmation)
python tests/test_runner.py --pattern real

# AutoGen real tests only
python tests/test_runner.py --pattern real-autogen

# CrewAI real tests only
python tests/test_runner.py --pattern real-crewai
```

**Full Execution Tests (Very Costly!):**
```bash
# AutoGen with actual praisonai.run() execution
python tests/test_runner.py --pattern full-autogen

# CrewAI with actual praisonai.run() execution  
python tests/test_runner.py --pattern full-crewai

# Both frameworks with full execution
python tests/test_runner.py --pattern full-frameworks
```

### Using pytest Directly

**Mock Tests:**
```bash
# All integration tests
python -m pytest tests/integration/ -v

# Specific framework
python -m pytest tests/integration/autogen/ -v
python -m pytest tests/integration/crewai/ -v
```

**Real Tests (Setup Only):**
```bash
# All real tests (requires API keys)
python -m pytest tests/e2e/ -v -m real

# Specific framework real tests
python -m pytest tests/e2e/autogen/ -v -m real
python -m pytest tests/e2e/crewai/ -v -m real
```

**Full Execution Tests:**
```bash
# Enable full execution and run with real-time output
export PRAISONAI_RUN_FULL_TESTS=true
python -m pytest tests/e2e/autogen/ -v -m real -s
python -m pytest tests/e2e/crewai/ -v -m real -s
```

## 🔐 API Key Setup

Real tests require API keys. Set at least one:

```bash
# Primary (required for most tests)
export OPENAI_API_KEY="sk-..."

# Optional alternatives
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."

# Enable full execution tests (💰 EXPENSIVE!)
export PRAISONAI_RUN_FULL_TESTS=true
```

## 🚨 Safety Features

### Mock Tests Safety
- ✅ No API calls made
- ✅ Always free to run
- ✅ Fast and reliable
- ✅ Safe for CI/CD

### Real Tests Safety
- ⚠️ **Cost warnings** before execution
- ⚠️ **User confirmation** required
- ⚠️ **Automatic skipping** without API keys
- ⚠️ **Minimal test design** to reduce costs

### Full Execution Tests Safety
- 🚨 **Double cost warnings** before execution
- 🚨 **"EXECUTE" confirmation** required
- 🚨 **Environment variable** protection
- 🚨 **Real-time output** to see actual execution
- 🚨 **Minimal YAML configs** to reduce costs

## 📋 Test Categories

### Unit Tests (`tests/unit/`)
- Core agent functionality
- Task management
- LLM integrations
- Configuration handling

### Mock Integration Tests (`tests/integration/`)
- Framework integration logic
- Agent/crew creation workflows
- Configuration validation
- Error handling

### Real E2E Tests (`tests/e2e/`)
- **Setup Tests**: Actual API setup validation
- **Full Execution Tests**: Complete workflow with praisonai.run()
- Environment verification
- Real framework integration

## 🎯 When to Use Each Test Type

### Use Mock Tests When:
- ✅ Developing new features
- ✅ Testing integration logic
- ✅ Running CI/CD pipelines
- ✅ Debugging configuration issues
- ✅ Daily development work

### Use Real Tests (Setup Only) When:
- ⚠️ Verifying API connectivity
- ⚠️ Testing configuration parsing
- ⚠️ Validating framework imports
- ⚠️ Quick integration checks

### Use Full Execution Tests When:
- 🚨 Preparing for major releases
- 🚨 Testing complete workflows
- 🚨 Debugging actual agent behavior
- 🚨 Validating production readiness
- 🚨 Manual quality assurance

## 📊 Test Commands Quick Reference

| Purpose | Command | Cost | Speed | Output |
|---------|---------|------|-------|--------|
| **Development Testing** | `python tests/test_runner.py --pattern fast` | Free | Fast | Basic |
| **Framework Integration** | `python tests/test_runner.py --pattern frameworks` | Free | Medium | Mock |
| **Real Setup Validation** | `python tests/test_runner.py --pattern real-autogen` | Low | Medium | Setup Only |
| **Full Execution** | `python tests/test_runner.py --pattern full-autogen` | High | Slow | Complete Logs |
| **Production Validation** | `python tests/test_runner.py --pattern full-frameworks` | High | Slow | Complete Logs | 