# Groq Intelligent Agents

This folder contains 10 specialized AI agents built using Groq models through the PraisonAI Agents framework.

## 🚀 Available Agents

### 1. Personal Branding & PR Agent
- **File**: `01_personal_branding_pr_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Build personal brands, manage public relations, create content strategies
- **Capabilities**: Social media management, content creation, media relations, reputation management

### 2. Supply Chain Optimization Agent
- **File**: `02_supply_chain_optimization_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Optimize supply chain operations and improve logistics efficiency
- **Capabilities**: Inventory management, supplier relationships, demand forecasting, transportation optimization

### 3. Event Planning & Management Agent
- **File**: `03_event_planning_management_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Plan and manage successful events from small gatherings to large conferences
- **Capabilities**: Venue selection, budget management, vendor coordination, timeline planning

### 4. Patent Research & Innovation Agent
- **File**: `04_patent_research_innovation_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Research patents and identify innovation opportunities
- **Capabilities**: Patent analysis, prior art searches, innovation strategy, intellectual property protection

### 5. Crisis Management & Communication Agent
- **File**: `05_crisis_management_communication_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Handle crisis situations and manage communications effectively
- **Capabilities**: Crisis response planning, stakeholder communication, reputation management

### 6. Language Learning & Translation Agent
- **File**: `06_language_learning_translation_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Help users learn languages and translate content
- **Capabilities**: Language learning strategies, grammar explanations, cultural context, translation accuracy

### 7. Environmental Impact Assessment Agent
- **File**: `07_environmental_impact_assessment_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Analyze environmental impacts and ensure sustainability compliance
- **Capabilities**: Carbon footprint analysis, sustainability reporting, environmental compliance

### 8. Digital Marketing & SEO Optimization Agent
- **File**: `08_digital_marketing_seo_optimization_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Optimize digital marketing campaigns and improve search engine rankings
- **Capabilities**: Keyword research, content optimization, social media marketing, PPC campaigns

### 9. Product Development & Innovation Agent
- **File**: `09_product_development_innovation_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Develop products from ideation to launch
- **Capabilities**: Product strategy, user research, MVP development, feature prioritization

### 10. Healthcare & Medical Research Agent
- **File**: `10_healthcare_medical_research_agent.py`
- **Model**: `groq/llama3.1-8b-instant`
- **Purpose**: Assist with medical research and healthcare insights
- **Capabilities**: Medical literature analysis, clinical trial research, health data interpretation

## 🛠️ Usage

### Prerequisites
```bash
pip install praisonaiagents
```

### Running an Agent
```python
# Example: Running the Personal Branding Agent
python 01_personal_branding_pr_agent.py
```

### Custom Usage
```python
from praisonaiagents import Agent

# Create agent instance
agent = Agent(
    instructions="Your agent instructions here",
    llm="groq/llama3.1-8b-instant"
)

# Start conversation
response = agent.start("Your message here")
```

## 🔧 Model Configuration

### Groq Models
- **Model**: `groq/llama3.1-8b-instant`
- **Provider**: Groq
- **Use Cases**: Fast inference, real-time applications, all specialized tasks

## 📁 File Structure
```
Groq Intelligent Agents/
├── README.md
├── 01_personal_branding_pr_agent.py
├── 02_supply_chain_optimization_agent.py
├── 03_event_planning_management_agent.py
├── 04_patent_research_innovation_agent.py
├── 05_crisis_management_communication_agent.py
├── 06_language_learning_translation_agent.py
├── 07_environmental_impact_assessment_agent.py
├── 08_digital_marketing_seo_optimization_agent.py
├── 09_product_development_innovation_agent.py
└── 10_healthcare_medical_research_agent.py
```

## 🎯 Key Features

- **Specialized Expertise**: Each agent is designed for specific domains
- **Unified Groq Model**: All agents use Groq for consistent, fast performance
- **Consistent Structure**: All agents follow the same implementation pattern
- **Easy Integration**: Built with PraisonAI Agents framework
- **Scalable**: Can be extended with additional tools and capabilities

## 🔄 Model Configuration

- **All Agents**: Use `groq/llama3.1-8b-instant`
- **Provider**: Groq
- **Benefits**: Fast inference, real-time applications, consistent performance across all specialized tasks 