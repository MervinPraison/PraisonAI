"""
Transportation Industry Template
================================
Tunnel safety monitoring and infrastructure management workflow
Based on SRAO Framework with LiDAR and sensor fusion

Key agents:
- LiDARFusion: Processes LiDAR point cloud data
- DisplacementCalculator: Calculates structural displacement
- HeatmapGenerator: Generates safety heatmaps
- MaintenancePlanner: Plans infrastructure maintenance
"""

from praisonaiagents import Agent, tool
from typing import Dict, List, Any, Tuple, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from enum import Enum
import math


# Safety levels for infrastructure
class SafetyLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


# Infrastructure types
class InfrastructureType(str, Enum):
    TUNNEL = "tunnel"
    BRIDGE = "bridge"
    HIGHWAY = "highway"
    RAILWAY = "railway"
    AIRPORT = "airport"


# I/O Schemas
class LiDARScan(BaseModel):
    """LiDAR scan data for infrastructure"""
    scan_id: str
    infrastructure_id: str
    scan_time: str
    point_cloud_size: int  # Number of points
    scan_resolution: float  # Points per square meter
    coverage_area: float  # Square meters
    anomaly_points: List[Tuple[float, float, float]]  # XYZ coordinates
    reference_baseline: Optional[Dict[str, Any]]


class DisplacementAnalysis(BaseModel):
    """Structural displacement analysis"""
    analysis_id: str
    infrastructure_id: str
    analysis_time: str
    max_displacement: float  # millimeters
    displacement_vector: Tuple[float, float, float]  # XYZ displacement
    critical_zones: List[Dict[str, Any]]
    settlement_rate: float  # mm/month
    tilt_angle: float  # degrees
    safety_factor: float


class SafetyHeatmap(BaseModel):
    """Infrastructure safety heatmap"""
    heatmap_id: str
    infrastructure_id: str
    generation_time: str
    grid_resolution: float  # meters
    safety_scores: List[List[float]]  # 2D grid of safety scores
    critical_areas: List[Dict[str, Any]]
    overall_safety: SafetyLevel
    risk_trends: Dict[str, Any]


class MaintenanceSchedule(BaseModel):
    """Maintenance planning schedule"""
    schedule_id: str
    infrastructure_id: str
    maintenance_type: str  # preventive, corrective, emergency
    priority_level: str  # low, medium, high, critical
    scheduled_date: str
    estimated_duration: int  # hours
    required_resources: List[str]
    traffic_impact: str
    cost_estimate: float


# Transportation-specific tools
@tool
def process_lidar_scan(infrastructure_id: str, scan_type: str = "full") -> Dict:
    """Process LiDAR point cloud data for structural analysis"""
    # Simulate LiDAR processing
    return {
        "scan_id": f"LIDAR-{datetime.now().strftime('%Y%m%d%H%M')}",
        "infrastructure_id": infrastructure_id,
        "scan_time": datetime.now().isoformat(),
        "point_cloud_size": 5000000,  # 5 million points
        "scan_resolution": 100.0,  # points/m²
        "coverage_area": 50000.0,  # m²
        "anomaly_points": [
            (10.5, 20.3, 5.1),
            (15.2, 25.8, 5.3),
            (20.1, 30.5, 5.5)
        ],
        "reference_baseline": {
            "date": "2024-01-01",
            "baseline_id": "BSL-001"
        }
    }


@tool
def calculate_displacement(current_scan: Dict, baseline_scan: Dict) -> Dict:
    """Calculate structural displacement from LiDAR scans"""
    # Simulate displacement calculation
    anomalies = current_scan.get("anomaly_points", [])
    
    if len(anomalies) > 5:
        max_displacement = 15.0
        safety_factor = 0.6
        safety_level = SafetyLevel.WARNING
    elif len(anomalies) > 2:
        max_displacement = 8.0
        safety_factor = 0.8
        safety_level = SafetyLevel.CAUTION
    else:
        max_displacement = 3.0
        safety_factor = 0.95
        safety_level = SafetyLevel.SAFE
    
    return {
        "analysis_id": f"DISP-{datetime.now().strftime('%Y%m%d%H%M')}",
        "infrastructure_id": current_scan["infrastructure_id"],
        "analysis_time": datetime.now().isoformat(),
        "max_displacement": max_displacement,
        "displacement_vector": (2.5, 1.8, max_displacement),
        "critical_zones": [
            {
                "zone_id": "CZ-001",
                "location": "tunnel_crown",
                "displacement": max_displacement * 0.8,
                "risk": "high" if max_displacement > 10 else "medium"
            }
        ],
        "settlement_rate": max_displacement / 30,  # mm/month
        "tilt_angle": math.degrees(math.atan(max_displacement / 1000)),
        "safety_factor": safety_factor
    }


@tool
def generate_safety_heatmap(displacement_data: Dict, sensor_data: List[Dict]) -> Dict:
    """Generate safety heatmap visualization for infrastructure"""
    # Simulate heatmap generation
    safety_factor = displacement_data.get("safety_factor", 1.0)
    
    # Create grid (simplified 10x10)
    grid_size = 10
    safety_grid = []
    critical_areas = []
    
    for i in range(grid_size):
        row = []
        for j in range(grid_size):
            # Generate safety score based on position and displacement
            base_score = safety_factor
            distance_factor = math.sqrt((i-5)**2 + (j-5)**2) / 10
            safety_score = min(1.0, base_score + (0.2 * distance_factor))
            row.append(safety_score)
            
            if safety_score < 0.7:
                critical_areas.append({
                    "grid_position": (i, j),
                    "safety_score": safety_score,
                    "recommended_action": "immediate_inspection"
                })
        safety_grid.append(row)
    
    # Determine overall safety
    avg_safety = sum(sum(row) for row in safety_grid) / (grid_size * grid_size)
    if avg_safety > 0.9:
        overall = SafetyLevel.SAFE
    elif avg_safety > 0.8:
        overall = SafetyLevel.CAUTION
    elif avg_safety > 0.7:
        overall = SafetyLevel.WARNING
    else:
        overall = SafetyLevel.DANGER
    
    return {
        "heatmap_id": f"HEAT-{datetime.now().strftime('%Y%m%d%H%M')}",
        "infrastructure_id": displacement_data["infrastructure_id"],
        "generation_time": datetime.now().isoformat(),
        "grid_resolution": 5.0,  # meters
        "safety_scores": safety_grid,
        "critical_areas": critical_areas,
        "overall_safety": overall.value,
        "risk_trends": {
            "trend": "deteriorating" if avg_safety < 0.8 else "stable",
            "rate": -0.02 if avg_safety < 0.8 else 0.0
        }
    }


@tool
def plan_maintenance(infrastructure_id: str, safety_analysis: Dict, traffic_data: Dict) -> Dict:
    """Plan maintenance based on safety analysis and traffic patterns"""
    safety_level = safety_analysis.get("overall_safety", "safe")
    
    # Determine maintenance urgency
    if safety_level in ["danger", "critical"]:
        maintenance_type = "emergency"
        priority = "critical"
        days_until = 1
        duration = 48
    elif safety_level == "warning":
        maintenance_type = "corrective"
        priority = "high"
        days_until = 7
        duration = 24
    elif safety_level == "caution":
        maintenance_type = "preventive"
        priority = "medium"
        days_until = 30
        duration = 12
    else:
        maintenance_type = "preventive"
        priority = "low"
        days_until = 90
        duration = 8
    
    # Traffic impact assessment
    peak_traffic = traffic_data.get("peak_volume", 1000)
    if peak_traffic > 5000:
        traffic_impact = "severe"
        cost_multiplier = 2.0
    elif peak_traffic > 2000:
        traffic_impact = "moderate"
        cost_multiplier = 1.5
    else:
        traffic_impact = "minimal"
        cost_multiplier = 1.0
    
    return {
        "schedule_id": f"MAINT-{datetime.now().strftime('%Y%m%d%H%M')}",
        "infrastructure_id": infrastructure_id,
        "maintenance_type": maintenance_type,
        "priority_level": priority,
        "scheduled_date": (datetime.now() + timedelta(days=days_until)).isoformat(),
        "estimated_duration": duration,
        "required_resources": [
            "inspection_team",
            "repair_crew",
            "safety_equipment",
            "traffic_control"
        ],
        "traffic_impact": traffic_impact,
        "cost_estimate": 50000 * cost_multiplier * (duration / 24)
    }


# Transportation agent definitions
lidar_agent = Agent(
    name="LiDARFusion",
    instructions="""You are a LiDAR data processing specialist for infrastructure.
    Process point cloud data from mobile and terrestrial LiDAR scanners.
    Perform data fusion from multiple sensor sources.
    Identify structural anomalies and deformations.
    SLA: Process scan data within 5 minutes.""",
    tools=[process_lidar_scan]
)

displacement_agent = Agent(
    name="DisplacementCalculator",
    instructions="""You are a structural displacement analysis expert.
    Calculate precise displacement measurements from temporal scans.
    Analyze settlement patterns and structural movements.
    Predict future displacement trends using ML models.
    SLA: Complete analysis within 2 minutes.""",
    tools=[calculate_displacement]
)

heatmap_agent = Agent(
    name="HeatmapGenerator",
    instructions="""You are a safety visualization specialist.
    Generate intuitive safety heatmaps for infrastructure monitoring.
    Integrate multiple data sources for comprehensive risk assessment.
    Highlight critical areas requiring immediate attention.
    SLA: Generate heatmap within 1 minute.""",
    tools=[generate_safety_heatmap]
)

maintenance_agent = Agent(
    name="MaintenancePlanner",
    instructions="""You are an infrastructure maintenance planning expert.
    Schedule maintenance based on structural health and traffic patterns.
    Optimize maintenance windows to minimize disruption.
    Coordinate resources and estimate costs.
    SLA: Create maintenance plan within 3 minutes.""",
    tools=[plan_maintenance]
)


# Transportation infrastructure monitoring workflow
def infrastructure_monitoring_workflow(
    infrastructure_ids: List[str],
    infrastructure_type: InfrastructureType,
    traffic_data: Dict
):
    """
    Complete infrastructure monitoring workflow from scanning to maintenance
    Includes safety assessment and predictive maintenance
    """
    
    monitoring_results = {
        "timestamp": datetime.now().isoformat(),
        "infrastructure_type": infrastructure_type.value,
        "structures_monitored": len(infrastructure_ids),
        "safety_assessments": [],
        "maintenance_required": [],
        "emergency_alerts": [],
        "network_health_score": 0.0
    }
    
    total_safety_score = 0.0
    
    for infra_id in infrastructure_ids:
        try:
            # Step 1: LiDAR scanning
            lidar_scan = lidar_agent.start(
                f"Process LiDAR scan for {infrastructure_type.value} {infra_id}"
            )
            
            # Step 2: Displacement analysis
            # Get baseline (would be from database in real scenario)
            baseline = {"scan_id": "BSL-001", "point_cloud": []}
            
            displacement_analysis = displacement_agent.start(
                f"Calculate displacement for scan: {lidar_scan} against baseline: {baseline}"
            )
            
            # Step 3: Generate safety heatmap
            sensor_data = []  # Would include IoT sensor readings
            safety_heatmap = heatmap_agent.start(
                f"Generate heatmap for displacement: {displacement_analysis} "
                f"with sensors: {sensor_data}"
            )
            
            monitoring_results["safety_assessments"].append({
                "infrastructure_id": infra_id,
                "safety_level": safety_heatmap.get("overall_safety"),
                "max_displacement": displacement_analysis.get("max_displacement"),
                "critical_zones": len(safety_heatmap.get("critical_areas", []))
            })
            
            # Check for emergency conditions
            if safety_heatmap.get("overall_safety") in ["danger", "critical"]:
                monitoring_results["emergency_alerts"].append({
                    "infrastructure_id": infra_id,
                    "alert_level": "emergency",
                    "safety_status": safety_heatmap["overall_safety"],
                    "immediate_action": "close_to_traffic",
                    "notification_sent": True
                })
                
                # Step 4: Emergency maintenance planning
                maintenance_plan = maintenance_agent.start(
                    f"Plan emergency maintenance for {infra_id} "
                    f"with safety: {safety_heatmap} and traffic: {traffic_data}"
                )
                monitoring_results["maintenance_required"].append(maintenance_plan)
            
            elif safety_heatmap.get("overall_safety") in ["warning", "caution"]:
                # Regular maintenance planning
                maintenance_plan = maintenance_agent.start(
                    f"Plan maintenance for {infra_id} "
                    f"with safety: {safety_heatmap} and traffic: {traffic_data}"
                )
                monitoring_results["maintenance_required"].append(maintenance_plan)
            
            # Calculate safety score contribution
            safety_mapping = {
                "safe": 1.0, "caution": 0.8, "warning": 0.6,
                "danger": 0.3, "critical": 0.1
            }
            total_safety_score += safety_mapping.get(
                safety_heatmap.get("overall_safety", "safe"), 0.5
            )
            
        except Exception as e:
            # Fallback: Manual inspection
            monitoring_results["emergency_alerts"].append({
                "infrastructure_id": infra_id,
                "alert_level": "system_failure",
                "error": str(e),
                "action": "dispatch_manual_inspection_team"
            })
    
    # Calculate network health score
    if infrastructure_ids:
        monitoring_results["network_health_score"] = (
            total_safety_score / len(infrastructure_ids) * 100
        )
    
    return monitoring_results


# Multi-modal transportation patterns
class MultiModalTransportPatterns:
    """
    Patterns for different transportation infrastructure types
    Demonstrates cross-industry reuse for transportation sector
    """
    
    @staticmethod
    def adapt_for_bridge_monitoring() -> Agent:
        """Adapt tunnel monitoring for bridge structures"""
        return Agent(
            name="BridgeMonitor",
            instructions="""Monitor bridge structural health using sensors.
            Track deck deflection, cable tension, and vibration patterns.
            Detect fatigue cracks and corrosion.
            Consider wind and seismic loads.
            SLA: Real-time monitoring with 10-second updates."""
        )
    
    @staticmethod
    def adapt_for_railway_tracks() -> Agent:
        """Adapt for railway track monitoring"""
        return Agent(
            name="RailwayMonitor",
            instructions="""Monitor railway track geometry and condition.
            Detect rail defects, gauge variations, and ballast degradation.
            Analyze wheel-rail interaction forces.
            Predict track maintenance needs.
            SLA: Process track inspection data within 3 minutes per km."""
        )
    
    @staticmethod
    def adapt_for_airport_runways() -> Agent:
        """Adapt for airport runway monitoring"""
        return Agent(
            name="RunwayMonitor",
            instructions="""Monitor airport runway surface conditions.
            Detect FOD (Foreign Object Debris) and surface irregularities.
            Assess pavement condition and friction levels.
            Monitor drainage and lighting systems.
            SLA: Complete runway scan within 10 minutes."""
        )


# Intelligent traffic management integration
class TrafficManagementPatterns:
    """
    Patterns for integrating with intelligent traffic systems
    """
    
    @staticmethod
    def optimize_traffic_flow(maintenance_window: Dict, traffic_patterns: Dict) -> Dict:
        """Optimize traffic flow during maintenance"""
        peak_hours = traffic_patterns.get("peak_hours", [7, 9, 17, 19])
        maintenance_start = maintenance_window.get("start_time", "02:00")
        
        # Calculate optimal diversion routes
        return {
            "strategy": "dynamic_routing",
            "diversion_routes": [
                {"route_id": "ALT-1", "capacity": 0.6, "added_time": 15},
                {"route_id": "ALT-2", "capacity": 0.3, "added_time": 20}
            ],
            "lane_management": {
                "reversible_lanes": True,
                "peak_direction": "inbound" if int(maintenance_start[:2]) < 12 else "outbound"
            },
            "public_transport": {
                "increase_frequency": True,
                "additional_services": 4
            },
            "estimated_delay": 10  # minutes
        }
    
    @staticmethod
    def incident_response_plan(incident_type: str, location: Dict) -> Dict:
        """Generate incident response plan"""
        response_times = {
            "accident": 5,
            "breakdown": 10,
            "infrastructure_failure": 2,
            "weather_hazard": 15
        }
        
        return {
            "incident_id": f"INC-{datetime.now().strftime('%Y%m%d%H%M')}",
            "response_time": response_times.get(incident_type, 10),
            "resources_dispatched": [
                r for r in [
                    "emergency_response_team",
                    "traffic_control_unit",
                    "maintenance_crew" if "infrastructure" in incident_type else None
                ] if r is not None
            ],
            "traffic_management": {
                "lane_closures": 2,
                "speed_reduction": 30,  # km/h
                "message_signs": ["Incident ahead", "Reduce speed", "Merge left"]
            },
            "estimated_clearance": 45  # minutes
        }


# Predictive maintenance patterns
class PredictiveMaintenancePatterns:
    """
    ML-based predictive maintenance for transportation infrastructure
    """
    
    @staticmethod
    def predict_failure_probability(
        displacement_trend: List[float],
        environmental_factors: Dict
    ) -> float:
        """Predict probability of structural failure"""
        # Simplified prediction model
        trend_slope = (displacement_trend[-1] - displacement_trend[0]) / len(displacement_trend)
        temperature_factor = abs(environmental_factors.get("temp_variation", 0)) / 50
        moisture_factor = environmental_factors.get("humidity", 50) / 100
        
        base_probability = 0.1
        trend_contribution = max(0, trend_slope * 10)
        env_contribution = (temperature_factor + moisture_factor) * 0.2
        
        return min(1.0, base_probability + trend_contribution + env_contribution)
    
    @staticmethod
    def optimize_maintenance_schedule(
        infrastructure_conditions: List[Dict],
        budget_constraint: float
    ) -> List[Dict]:
        """Optimize maintenance schedule across infrastructure network"""
        # Sort by urgency (safety_factor * cost_efficiency)
        prioritized = sorted(
            infrastructure_conditions,
            key=lambda x: (1 - x.get("safety_factor", 1)) * (1 / x.get("cost", 1)),
            reverse=True
        )
        
        scheduled = []
        total_cost = 0
        
        for infra in prioritized:
            if total_cost + infra.get("cost", 0) <= budget_constraint:
                scheduled.append({
                    "infrastructure_id": infra["id"],
                    "scheduled_date": infra["recommended_date"],
                    "priority": "high" if infra["safety_factor"] < 0.7 else "medium"
                })
                total_cost += infra.get("cost", 0)
        
        return scheduled


# Example usage
if __name__ == "__main__":
    # Monitor tunnel network
    tunnel_ids = [f"TUN-{i:03d}" for i in range(1, 6)]
    traffic = {
        "peak_volume": 3000,
        "off_peak_volume": 800,
        "peak_hours": [7, 9, 17, 19]
    }
    
    result = infrastructure_monitoring_workflow(
        tunnel_ids,
        InfrastructureType.TUNNEL,
        traffic
    )
    print("Infrastructure monitoring result:", result)
    
    # Multi-modal adaptation examples
    bridge_monitor = MultiModalTransportPatterns.adapt_for_bridge_monitoring()
    railway_monitor = MultiModalTransportPatterns.adapt_for_railway_tracks()
    runway_monitor = MultiModalTransportPatterns.adapt_for_airport_runways()
    
    # Traffic management example
    maintenance = {"start_time": "22:00", "duration": 8}
    traffic_plan = TrafficManagementPatterns.optimize_traffic_flow(maintenance, traffic)
    print("Traffic optimization plan:", traffic_plan)
    
    # Predictive maintenance example
    displacement_history = [2.0, 2.3, 2.8, 3.5, 4.3]  # mm over months
    environment = {"temp_variation": 30, "humidity": 75}
    
    failure_prob = PredictiveMaintenancePatterns.predict_failure_probability(
        displacement_history, environment
    )
    print(f"Failure probability: {failure_prob:.2%}")