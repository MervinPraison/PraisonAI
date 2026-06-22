# Industry Templates for PraisonAI

This directory contains industry-specific agent templates based on the SRAO Framework, providing pre-built workflows for rapid deployment of agent workforces across different industries.

## Overview

These templates demonstrate how PraisonAI can be used to create specialized agent teams for various industries, with **70% code reuse** across different sectors through shared patterns and abstractions.

## Available Templates

### 1. Manufacturing (`manufacturing_template.py`)
**Key Agents:**
- **ParseOrder**: Extracts and structures order information from various formats
- **CheckInventory**: Validates material availability and supply chain status  
- **OptimizeSchedule**: Optimizes production scheduling based on constraints
- **DefectDetect**: Quality control and defect detection

**Features:**
- Order processing with multiple input formats
- Real-time inventory management
- Production optimization algorithms
- Quality inspection with defect detection
- Fallback strategies for each critical step

### 2. Energy (`energy_template.py`)
**Key Agents:**
- **SCADAReader**: Processes SCADA telemetry data from wind turbines
- **VibrationAnalyzer**: Analyzes vibration patterns for predictive maintenance
- **PowerForecaster**: Predicts power generation based on weather and history
- **MaintenanceScheduler**: Schedules predictive maintenance

**Features:**
- Real-time wind farm monitoring
- Vibration-based fault detection
- Power generation forecasting
- Grid integration and load balancing
- Predictive maintenance scheduling

### 3. Healthcare (`healthcare_template.py`)
**Key Agents:**
- **VitalSignsCapture**: Processes patient vital signs from monitoring devices
- **EMRRetrieval**: Retrieves electronic medical records with HIPAA compliance
- **TriageRecommendation**: Provides ESI-based triage recommendations
- **ResourceAllocator**: Manages hospital resource allocation

**Features:**
- Emergency triage workflow
- HIPAA-compliant data handling
- Patient safety protocols
- Resource optimization
- Cross-department coordination

### 4. Agriculture (`agriculture_template.py`)
**Key Agents:**
- **MultispectralAnalyzer**: Analyzes multispectral imagery for crop health
- **DiseaseIdentifier**: Identifies crop diseases and pests using AI
- **SprayRecommender**: Recommends targeted spraying strategies
- **YieldPredictor**: Predicts crop yield based on conditions

**Features:**
- Precision agriculture with drone/satellite imagery
- Pest and disease early warning system
- Optimized chemical application
- Yield forecasting
- Sustainable farming patterns

### 5. Transportation (`transportation_template.py`)
**Key Agents:**
- **LiDARFusion**: Processes LiDAR point cloud data for infrastructure
- **DisplacementCalculator**: Calculates structural displacement
- **HeatmapGenerator**: Generates safety visualization heatmaps
- **MaintenancePlanner**: Plans infrastructure maintenance

**Features:**
- Tunnel/bridge safety monitoring
- LiDAR-based structural analysis
- Real-time safety assessment
- Traffic flow optimization
- Predictive maintenance scheduling

## Key Features Across All Templates

### 1. I/O Schemas
Each template includes Pydantic models for structured data handling:
- Input validation
- Type safety
- Clear data contracts between agents

### 2. SLA Requirements
Every agent has defined Service Level Agreements:
- Processing time requirements
- Response time guarantees
- Performance benchmarks

### 3. Fallback Strategies
Robust error handling with fallback mechanisms:
- Graceful degradation
- Manual intervention queues
- Conservative estimates when systems fail

### 4. Cross-Industry Patterns (70% Reuse)
Reusable base patterns that work across industries:
- Data parsing agents
- Resource availability checkers
- Optimization engines
- Inspection/quality control agents

## Usage Example

```python
from manufacturing_template import (
    order_parser,
    inventory_checker,
    schedule_optimizer,
    quality_inspector,
    manufacturing_workflow
)

# Process a manufacturing order
order_text = "Customer ABC needs 100 units of Product-XYZ by March 15th, high priority"
result = manufacturing_workflow(order_text)
print(result)
```

## Adapting Templates for Your Industry

### Using Base Patterns
Each template includes reusable pattern classes that can be adapted:

```python
from manufacturing_template import IndustryAgentPattern

# Create a custom data parser for any domain
custom_parser = IndustryAgentPattern.create_data_parser(
    name="CustomParser",
    domain="retail",
    sla_seconds=20
)

# Create a resource checker for any resource type
resource_checker = IndustryAgentPattern.create_resource_checker(
    name="StaffAvailability",
    resource_type="customer_service_staff",
    sla_seconds=3
)
```

### Creating Custom Workflows
Combine agents from different templates or create new ones:

```python
from praisonaiagents import Agent, tool

# Define custom tools
@tool
def custom_analysis(data: str) -> Dict:
    """Your custom analysis logic"""
    return {"result": "analyzed"}

# Create custom agent
custom_agent = Agent(
    name="CustomAnalyzer",
    instructions="Your specific instructions",
    tools=[custom_analysis]
)
```

## Integration with PraisonAI Core

These templates are built on top of PraisonAI's core Agent framework:

```python
from praisonaiagents import Agent, tool, AgentTeam, Task

# Combine multiple industry agents into a team
team = AgentTeam(
    agents=[order_parser, inventory_checker, schedule_optimizer],
    tasks=[
        Task(name="parse", agent=order_parser),
        Task(name="check", agent=inventory_checker),
        Task(name="optimize", agent=schedule_optimizer)
    ]
)
```

## Best Practices

1. **Start with Templates**: Use these as starting points and customize for your specific needs
2. **Maintain SLAs**: Define clear performance requirements for each agent
3. **Implement Fallbacks**: Always have fallback strategies for critical operations
4. **Use Type Safety**: Leverage Pydantic models for data validation
5. **Monitor Performance**: Track agent performance against SLAs
6. **Iterate and Improve**: Continuously refine based on real-world usage

## Contributing

To add a new industry template:

1. Follow the existing template structure
2. Include all key components:
   - I/O Schemas (Pydantic models)
   - Agent definitions with SLAs
   - Tools for agent capabilities
   - Complete workflow function
   - Fallback strategies
   - Cross-industry patterns
3. Add comprehensive documentation
4. Include usage examples

## License

These templates are part of the PraisonAI project and follow the same licensing terms.

## References

Based on the [SRAO Framework](https://github.com/beixuan577/SRAO-Framework) (MIT License)