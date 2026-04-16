# n8n Integration Test Guide

This document describes how to set up live n8n integration tests for the PraisonAI n8n integration feature.

## GitHub Actions Configuration

To add live n8n integration testing to your CI/CD pipeline, create a workflow file `.github/workflows/n8n-integration.yml`:

```yaml
name: n8n Integration Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
    paths:
      - 'src/praisonai/praisonai/n8n/**'
      - 'src/praisonai/tests/test_n8n_integration.py'

jobs:
  n8n-integration:
    runs-on: ubuntu-latest
    
    services:
      n8n:
        image: docker.n8n.io/n8nio/n8n
        ports:
          - 5678:5678
        env:
          N8N_BASIC_AUTH_ACTIVE: true
          N8N_BASIC_AUTH_USER: admin
          N8N_BASIC_AUTH_PASSWORD: password
          DB_TYPE: sqlite
          N8N_ENCRYPTION_KEY: test-encryption-key
        options: >-
          --health-cmd "wget --no-verbose --tries=1 --spider http://localhost:5678 || exit 1"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: 3.11
          
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          cd src/praisonai && pip install -e ".[n8n]"
          pip install pytest
          
      - name: Wait for n8n to be ready
        run: |
          timeout 120 bash -c 'until curl -f http://localhost:5678; do sleep 2; done'
          
      - name: Run n8n integration tests
        run: |
          cd src/praisonai
          pytest tests/test_n8n_integration.py -v -m integration
        env:
          N8N_URL: http://localhost:5678
          N8N_USER: admin
          N8N_PASSWORD: password

  test-workflow-creation:
    runs-on: ubuntu-latest
    needs: n8n-integration
    
    services:
      n8n:
        image: docker.n8n.io/n8nio/n8n
        ports:
          - 5678:5678
        env:
          N8N_BASIC_AUTH_ACTIVE: true
          N8N_BASIC_AUTH_USER: admin
          N8N_BASIC_AUTH_PASSWORD: password
          DB_TYPE: sqlite
          N8N_ENCRYPTION_KEY: test-encryption-key
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: 3.11
          
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          cd src/praisonai && pip install -e ".[n8n]"
          
      - name: Test workflow creation and execution
        run: |
          cd src/praisonai
          python -c "
          from praisonai.n8n import YAMLToN8nConverter, N8nClient
          import yaml
          import os
          
          # Test YAML workflow
          test_workflow = {
              'name': 'Test Workflow',
              'agents': {
                  'researcher': {'instructions': 'Research topics'},
                  'writer': {'instructions': 'Write content'}
              },
              'steps': [
                  'researcher',
                  {'agent': 'writer', 'action': 'write_summary'}
              ]
          }
          
          # Convert to n8n format
          converter = YAMLToN8nConverter()
          n8n_workflow = converter.convert(test_workflow)
          
          # Test connection to n8n
          client = N8nClient(
              base_url=os.getenv('N8N_URL', 'http://localhost:5678'),
              auth=('admin', 'password')
          )
          
          # Create workflow
          created = client.create_workflow('test-workflow', n8n_workflow)
          print(f'Created workflow: {created}')
          
          # List workflows
          workflows = client.list_workflows()
          print(f'Available workflows: {len(workflows)}')
          
          print('✅ Live n8n integration test passed!')
          "
        env:
          N8N_URL: http://localhost:5678
```

## Test Markers

To properly organize the integration tests, add these pytest markers to your test file:

```python
import pytest

@pytest.mark.integration
def test_live_n8n_workflow_creation():
    \"\"\"Test actual workflow creation with live n8n instance.\"\"\"
    # Test implementation here
    pass

@pytest.mark.integration
def test_live_n8n_execution():
    \"\"\"Test workflow execution with live n8n instance.\"\"\"
    # Test implementation here
    pass
```

## Running Tests Locally

To run the integration tests locally:

1. Start n8n with Docker:
```bash
docker run -d --name n8n -p 5678:5678 \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=password \
  docker.n8n.io/n8nio/n8n
```

2. Run the tests:
```bash
cd src/praisonai
pytest tests/test_n8n_integration.py -v -m integration
```

## Environment Variables

The integration tests use these environment variables:

- `N8N_URL`: n8n instance URL (default: http://localhost:5678)
- `N8N_USER`: Basic auth username (default: admin)
- `N8N_PASSWORD`: Basic auth password (default: password)
- `N8N_API_KEY`: Alternative to basic auth (optional)

## Test Coverage

The integration tests should cover:

- [ ] Workflow creation via API
- [ ] Workflow execution
- [ ] YAML to n8n JSON conversion with real data
- [ ] n8n JSON to YAML reverse conversion
- [ ] Loop pattern with splitInBatches nodes
- [ ] Route pattern with switch nodes
- [ ] Parallel execution patterns
- [ ] Error handling and recovery

## Notes

- Tests marked with `@pytest.mark.integration` require a live n8n instance
- Unit tests (without the marker) can run without n8n
- The n8n Docker service includes health checks to ensure readiness
- Basic authentication is used for simplicity in tests
- SQLite is used as the database for test isolation