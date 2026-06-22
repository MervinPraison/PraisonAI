"""
Manufacturing Industry Template
================================
Order scheduling, inventory management, and quality inspection workflow
Based on SRAO Framework patterns with 70% cross-industry reuse

Key agents:
- ParseOrder: Extracts order details from various formats
- CheckInventory: Validates material availability
- OptimizeSchedule: Optimizes production scheduling
- DefectDetect: Quality control and defect detection
"""

from praisonaiagents import Agent, tool
from typing import Dict, List, Any
from pydantic import BaseModel


# I/O Schemas
class OrderDetails(BaseModel):
    """Structured order information"""
    order_id: str
    customer_id: str
    product_id: str
    quantity: int
    priority: str = "normal"  # normal, high, urgent
    due_date: str
    requirements: Dict[str, Any] = {}


class InventoryStatus(BaseModel):
    """Material availability status"""
    material_id: str
    available_quantity: int
    reorder_level: int
    supplier_lead_time: int
    location: str


class ProductionSchedule(BaseModel):
    """Optimized production schedule"""
    schedule_id: str
    production_line: str
    start_time: str
    end_time: str
    assigned_workers: List[str]
    estimated_completion: str
    bottleneck_analysis: Dict[str, Any] = {}


class QualityReport(BaseModel):
    """Quality inspection results"""
    batch_id: str
    inspection_time: str
    defect_rate: float
    defect_types: List[str]
    passed: bool
    recommendations: List[str]


# Tools for agents
@tool
def extract_order_details(text: str) -> Dict:
    """Extract structured order information from unstructured text"""
    # Simulate order parsing logic
    return {
        "order_id": "ORD-2024-001",
        "customer_id": "CUST-123",
        "product_id": "PROD-456",
        "quantity": 100,
        "priority": "high",
        "due_date": "2024-03-15",
        "requirements": {"material": "steel", "finish": "polished"}
    }


@tool
def check_material_availability(product_id: str, quantity: int) -> Dict:
    """Check if materials are available for production"""
    # Simulate inventory check
    return {
        "material_id": "MAT-789",
        "available_quantity": 500,
        "reorder_level": 100,
        "supplier_lead_time": 7,
        "location": "Warehouse-A"
    }


@tool
def calculate_optimal_schedule(order: Dict, inventory: Dict) -> Dict:
    """Calculate optimal production schedule based on constraints"""
    # Simulate scheduling optimization
    return {
        "schedule_id": "SCH-2024-001",
        "production_line": "Line-3",
        "start_time": "2024-03-10T08:00:00",
        "end_time": "2024-03-14T17:00:00",
        "assigned_workers": ["Worker-001", "Worker-002"],
        "estimated_completion": "2024-03-14T16:30:00",
        "bottleneck_analysis": {
            "critical_path": "Assembly",
            "buffer_time": 2.5
        }
    }


@tool
def perform_quality_inspection(batch_id: str) -> Dict:
    """Perform automated quality inspection on production batch"""
    # Simulate quality control
    return {
        "batch_id": batch_id,
        "inspection_time": "2024-03-14T17:00:00",
        "defect_rate": 0.02,
        "defect_types": ["surface_scratch", "dimension_variance"],
        "passed": True,
        "recommendations": [
            "Adjust machine calibration on Line-3",
            "Increase inspection frequency for next batch"
        ]
    }


# Agent Definitions with SLA requirements
order_parser = Agent(
    name="ParseOrder",
    instructions="""You are an order parsing specialist. Extract and structure order information 
    from various formats (email, PDF, API). Ensure all required fields are captured and validated.
    SLA: Process within 30 seconds per order.""",
    tools=[extract_order_details]
)

inventory_checker = Agent(
    name="CheckInventory",
    instructions="""You are an inventory management specialist. Verify material availability,
    check reorder points, and identify potential supply chain issues.
    SLA: Real-time response within 5 seconds.""",
    tools=[check_material_availability]
)

schedule_optimizer = Agent(
    name="OptimizeSchedule",
    instructions="""You are a production scheduling expert. Optimize production schedules
    based on order priority, resource availability, and constraints. Minimize idle time
    and maximize throughput.
    SLA: Generate schedule within 2 minutes for complex orders.""",
    tools=[calculate_optimal_schedule]
)

quality_inspector = Agent(
    name="DefectDetect",
    instructions="""You are a quality control specialist. Perform automated inspections,
    detect defects using vision analysis, and provide improvement recommendations.
    SLA: Complete inspection within 1 minute per batch.""",
    tools=[perform_quality_inspection]
)


# Workflow with fallback strategies
def manufacturing_workflow(order_text: str):
    """
    Complete manufacturing workflow from order to quality control
    Includes fallback strategies for each critical step
    """
    
    # Step 1: Parse order with fallback
    try:
        order_details = order_parser.start(f"Parse this order: {order_text}")
        if not order_details:
            # Fallback: Manual review queue
            return {"status": "manual_review_required", "reason": "order_parsing_failed"}
    except Exception as e:
        return {"status": "error", "stage": "order_parsing", "error": str(e)}
    
    # Step 2: Check inventory with fallback
    try:
        inventory_status = inventory_checker.start(
            f"Check materials for order: {order_details}"
        )
        if not inventory_status:
            # Fallback: Alternative supplier check
            return {"status": "alternative_supplier_needed", "order": order_details}
    except Exception as e:
        # Fallback: Conservative estimate with safety margin
        inventory_status = {"estimated": True, "safety_margin": 1.5}
    
    # Step 3: Optimize schedule with fallback
    try:
        schedule = schedule_optimizer.start(
            f"Create schedule for order {order_details} with inventory {inventory_status}"
        )
        if not schedule:
            # Fallback: Standard scheduling template
            schedule = {"template": "standard", "priority": "normal"}
    except Exception as e:
        # Fallback: Queue for next available slot
        schedule = {"status": "queued", "estimated_start": "next_available"}
    
    # Step 4: Quality inspection with fallback
    try:
        quality_report = quality_inspector.start(
            f"Inspect batch for schedule {schedule}"
        )
        if not quality_report:
            # Fallback: Manual inspection required
            quality_report = {"requires_manual": True, "inspector_assigned": "QC-Team-1"}
    except Exception as e:
        # Fallback: Quarantine for review
        quality_report = {"status": "quarantined", "review_required": True}
    
    return {
        "status": "completed",
        "order": order_details,
        "inventory": inventory_status,
        "schedule": schedule,
        "quality": quality_report
    }


# Cross-industry reusable patterns (70% reuse)
class IndustryAgentPattern:
    """
    Base pattern reusable across industries
    Provides common agent capabilities that can be specialized
    """
    
    @staticmethod
    def create_data_parser(name: str, domain: str, sla_seconds: int = 30):
        """Create a data parsing agent for any domain"""
        return Agent(
            name=name,
            instructions=f"""You are a {domain} data parsing specialist.
            Extract and structure information from various formats.
            Validate all required fields according to {domain} standards.
            SLA: Process within {sla_seconds} seconds."""
        )
    
    @staticmethod
    def create_resource_checker(name: str, resource_type: str, sla_seconds: int = 5):
        """Create a resource availability checker for any resource type"""
        return Agent(
            name=name,
            instructions=f"""You are a {resource_type} availability specialist.
            Verify {resource_type} availability and identify constraints.
            Provide real-time status and alternative options if needed.
            SLA: Response within {sla_seconds} seconds."""
        )
    
    @staticmethod
    def create_optimizer(name: str, optimization_target: str, sla_minutes: int = 2):
        """Create an optimization agent for any target metric"""
        return Agent(
            name=name,
            instructions=f"""You are an optimization expert for {optimization_target}.
            Find optimal solutions considering all constraints and priorities.
            Minimize waste and maximize efficiency.
            SLA: Generate solution within {sla_minutes} minutes."""
        )
    
    @staticmethod
    def create_inspector(name: str, inspection_type: str, sla_minutes: int = 1):
        """Create an inspection agent for any quality metric"""
        return Agent(
            name=name,
            instructions=f"""You are a {inspection_type} inspection specialist.
            Perform automated analysis and detect anomalies.
            Provide actionable recommendations for improvement.
            SLA: Complete inspection within {sla_minutes} minute(s)."""
        )


# Example usage
if __name__ == "__main__":
    # Create a manufacturing workflow instance
    order = "Customer ABC needs 100 units of Product-XYZ by March 15th, high priority"
    
    # Option 1: Use specialized agents
    result = manufacturing_workflow(order)
    print("Manufacturing workflow result:", result)
    
    # Option 2: Use reusable patterns for other industries
    # These patterns can be adapted for Energy, Healthcare, Agriculture, Transportation
    energy_parser = IndustryAgentPattern.create_data_parser(
        "EnergyDataParser", "wind farm telemetry", sla_seconds=10
    )
    
    healthcare_checker = IndustryAgentPattern.create_resource_checker(
        "BedAvailability", "hospital bed", sla_seconds=3
    )
    
    agriculture_optimizer = IndustryAgentPattern.create_optimizer(
        "IrrigationOptimizer", "water usage", sla_minutes=5
    )
    
    transport_inspector = IndustryAgentPattern.create_inspector(
        "TunnelSafety", "structural integrity", sla_minutes=2
    )