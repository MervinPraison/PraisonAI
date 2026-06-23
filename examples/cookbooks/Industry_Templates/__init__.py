"""
Industry Templates for PraisonAI
================================

Pre-built agent templates for rapid deployment across different industries.
Based on SRAO Framework with 70% cross-industry code reuse.

Available templates:
- Manufacturing: Order processing, inventory, scheduling, quality control
- Energy: Wind farm monitoring, predictive maintenance, power forecasting
- Healthcare: Emergency triage, EMR retrieval, resource allocation
- Agriculture: Precision farming, pest detection, yield prediction
- Transportation: Infrastructure monitoring, safety assessment, maintenance

Example usage:
    from Industry_Templates.manufacturing_template import manufacturing_workflow
    
    result = manufacturing_workflow("Customer order text")
"""

__version__ = "1.0.0"
__author__ = "PraisonAI Team"

# Import the modules so they're accessible via the package
from . import manufacturing_template
from . import energy_template
from . import healthcare_template
from . import agriculture_template
from . import transportation_template

# Export commonly used items for convenience
__all__ = [
    "manufacturing_template",
    "energy_template", 
    "healthcare_template",
    "agriculture_template",
    "transportation_template"
]