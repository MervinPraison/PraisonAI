# Secondary Market Research Agent System

A comprehensive multi-agent system for generating customized secondary market research reports with FastAPI integration.

## 🎯 Features

- **Multi-Agent Research System**: Specialized agents for different research areas
- **Customizable Parameters**: Company, geography, industry, and research sections
- **Comprehensive Reports**: Market overview, competitive analysis, financial performance, growth opportunities, and risk assessment
- **FastAPI Integration**: Production-ready REST API
- **Professional Output**: Business-ready reports suitable for decision-making

## 📁 Files

- `secondary-market-research.py` - Main Python implementation
- `secondary-market-research-api.py` - FastAPI web service
- `secondary_market_research_agents.yaml` - YAML configuration
- `secondary_market_research_agents.ipynb` - Jupyter notebook examples

## 🚀 Quick Start

### 1. Python Implementation

```python
from praisonaiagents import Agent, Task, PraisonAIAgents, Tools
import asyncio

# Configure research parameters
config = MarketResearchConfig(
    company="Tesla",
    geography="North America", 
    industry="Electric Vehicles",
    sections=["market_overview", "competitive_analysis", "financial_performance"]
)

# Run research
results = await run_market_research(config)
```

### 2. FastAPI Web Service

```bash
# Start the API server
uvicorn secondary-market-research-api:app --reload --port 8000

# Visit API documentation
http://localhost:8000/docs
```

### 3. YAML Configuration

```yaml
framework: "crewai"
topic: "Secondary Market Research Analysis"

variables:
  company: "Tesla"
  geography: "North America" 
  industry: "Electric Vehicles"

roles:
  market_overview_specialist:
    role: "Market Overview Specialist"
    # ... configuration details
```

## 📊 Research Sections

Choose from the following research sections:

- **market_overview**: Market size, trends, and growth drivers
- **competitive_analysis**: Competitor analysis and market positioning  
- **financial_performance**: Financial metrics and benchmarking
- **growth_opportunities**: Strategic growth vectors and opportunities
- **risk_assessment**: Risk factors and mitigation strategies

## 🌍 Use Cases

### Technology Companies
```python
config = MarketResearchConfig(
    company="OpenAI",
    geography="United States",
    industry="Artificial Intelligence",
    sections=["market_overview", "competitive_analysis", "growth_opportunities"]
)
```

### Automotive Industry
```python
config = MarketResearchConfig(
    company="BMW",
    geography="Europe", 
    industry="Luxury Automobiles",
    sections=["market_overview", "competitive_analysis", "financial_performance", "risk_assessment"]
)
```

### Healthcare/Pharmaceuticals
```python
config = MarketResearchConfig(
    company="Pfizer",
    geography="Global",
    industry="Pharmaceuticals", 
    sections=["market_overview", "competitive_analysis", "growth_opportunities", "risk_assessment"]
)
```

## 🔧 API Endpoints

### Generate Research Report
```http
POST /research/generate
Content-Type: application/json

{
  "company": "Tesla",
  "geography": "North America",
  "industry": "Electric Vehicles", 
  "sections": ["market_overview", "competitive_analysis"],
  "format": "json"
}
```

### Check Job Status
```http
GET /research/status/{job_id}
```

### Download Report
```http
GET /research/reports/{job_id}
```

### Get Templates
```http
GET /research/templates
```

## 📈 Output Format

The system generates comprehensive reports with the following structure:

```json
{
  "metadata": {
    "job_id": "uuid",
    "company": "Tesla",
    "geography": "North America",
    "industry": "Electric Vehicles",
    "generated_at": "2024-01-01T00:00:00Z"
  },
  "executive_summary": "...",
  "research_findings": {
    "market_overview_research": {
      "content": "Market analysis...",
      "agent": "Market Overview Specialist"
    },
    "competitive_analysis": {
      "content": "Competitive intelligence...", 
      "agent": "Competitive Intelligence Analyst"
    }
  }
}
```

## 🛠️ Installation

```bash
pip install praisonai[crewai]
pip install fastapi uvicorn
```

## ⚙️ Configuration

Set your API keys:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL_NAME="gpt-4o-mini"
```

## 📝 Customization

### Adding New Research Sections

1. Create a new agent in `create_market_research_agents()`
2. Add corresponding task in `create_research_tasks()`
3. Update the sections list in configuration

### Geographic Regions

Supported regions include:
- North America
- Europe  
- Asia Pacific
- Global
- Custom regions

### Industries

The system works across industries:
- Technology
- Automotive
- Healthcare/Pharmaceuticals
- Financial Services
- Retail/E-commerce
- Energy
- Manufacturing
- And more...

## 🎓 Examples

See the Jupyter notebook `secondary_market_research_agents.ipynb` for detailed examples including:

- YAML-based configuration
- Python API usage
- FastAPI integration
- Multiple industry examples
- Customization patterns

## 🚀 Production Deployment

For production use:

1. Deploy FastAPI with proper ASGI server (Gunicorn + Uvicorn)
2. Use Redis or database for job status storage
3. Implement proper error handling and logging
4. Add authentication and rate limiting
5. Set up monitoring and alerting

## 📄 License

This project is part of PraisonAI and follows the same licensing terms.