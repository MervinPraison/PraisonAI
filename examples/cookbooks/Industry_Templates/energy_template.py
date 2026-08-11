# praisonai: skip=true
"""
Energy Industry Template
========================
Wind farm monitoring and power optimization workflow
Based on SRAO Framework patterns with predictive maintenance

Key agents:
- SCADAReader: Processes SCADA telemetry data
- VibrationAnalyzer: Analyzes turbine vibration patterns
- PowerForecaster: Predicts power generation
- MaintenanceScheduler: Schedules predictive maintenance
"""

from praisonaiagents import Agent, tool
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta


# I/O Schemas
class TurbineData(BaseModel):
    """Wind turbine telemetry data"""
    turbine_id: str
    timestamp: str
    wind_speed: float  # m/s
    power_output: float  # MW
    rotor_speed: float  # RPM
    blade_pitch: float  # degrees
    nacelle_temperature: float  # Celsius
    vibration_level: float  # mm/s
    operational_status: str  # running, stopped, maintenance


class VibrationAnalysis(BaseModel):
    """Vibration analysis results"""
    turbine_id: str
    analysis_time: str
    vibration_rms: float
    frequency_peaks: List[float]
    anomaly_detected: bool
    failure_probability: float
    recommended_action: str


class PowerForecast(BaseModel):
    """Power generation forecast"""
    forecast_id: str
    start_time: str
    end_time: str
    predicted_output: List[float]  # MW per hour
    confidence_interval: float
    weather_factors: Dict[str, Any]
    grid_demand: float


class MaintenancePlan(BaseModel):
    """Maintenance scheduling plan"""
    plan_id: str
    turbine_id: str
    maintenance_type: str  # preventive, predictive, corrective
    scheduled_date: str
    estimated_duration: int  # hours
    required_parts: List[str]
    technician_team: str
    production_loss: float  # MW


# Tools for energy management
@tool
def read_scada_telemetry(turbine_id: str, time_range: str = "last_hour") -> Dict:
    """Read SCADA system telemetry for wind turbines"""
    # Simulate SCADA data reading
    return {
        "turbine_id": turbine_id,
        "timestamp": datetime.now().isoformat(),
        "wind_speed": 12.5,
        "power_output": 2.3,
        "rotor_speed": 16.8,
        "blade_pitch": 8.5,
        "nacelle_temperature": 45.2,
        "vibration_level": 3.2,
        "operational_status": "running"
    }


@tool
def analyze_vibration_patterns(turbine_data: Dict) -> Dict:
    """Analyze vibration patterns for early fault detection"""
    # Simulate vibration analysis
    vibration_level = turbine_data.get("vibration_level", 0)
    anomaly = vibration_level > 5.0  # Threshold for anomaly
    
    return {
        "turbine_id": turbine_data["turbine_id"],
        "analysis_time": datetime.now().isoformat(),
        "vibration_rms": vibration_level,
        "frequency_peaks": [10.5, 25.3, 50.0],  # Hz
        "anomaly_detected": anomaly,
        "failure_probability": min(vibration_level / 10.0, 1.0),
        "recommended_action": "immediate_inspection" if anomaly else "continue_monitoring"
    }


@tool
def forecast_power_generation(weather_data: Dict, historical_data: List) -> Dict:
    """Forecast power generation based on weather and historical patterns"""
    # Simulate power forecasting
    base_forecast = [2.0 + (i * 0.1) for i in range(24)]  # 24-hour forecast
    
    return {
        "forecast_id": f"FCST-{datetime.now().strftime('%Y%m%d%H%M')}",
        "start_time": datetime.now().isoformat(),
        "end_time": (datetime.now() + timedelta(hours=24)).isoformat(),
        "predicted_output": base_forecast,
        "confidence_interval": 0.85,
        "weather_factors": weather_data,
        "grid_demand": sum(base_forecast)
    }


@tool
def schedule_maintenance(turbine_id: str, maintenance_type: str, urgency: str = "normal") -> Dict:
    """Schedule maintenance based on condition monitoring"""
    # Calculate maintenance window
    if urgency == "urgent":
        scheduled_date = (datetime.now() + timedelta(days=1)).isoformat()
    else:
        scheduled_date = (datetime.now() + timedelta(days=7)).isoformat()
    
    return {
        "plan_id": f"MNT-{datetime.now().strftime('%Y%m%d%H%M')}",
        "turbine_id": turbine_id,
        "maintenance_type": maintenance_type,
        "scheduled_date": scheduled_date,
        "estimated_duration": 4,
        "required_parts": ["bearing_set", "lubricant", "filter"],
        "technician_team": "Team-A",
        "production_loss": 8.0  # MW lost during maintenance
    }


# Agent Definitions with SLA requirements
scada_reader = Agent(
    name="SCADAReader",
    instructions="""You are a SCADA system specialist for wind farms.
    Process real-time telemetry data from wind turbines.
    Identify operational anomalies and performance deviations.
    SLA: Process telemetry within 1 second for real-time monitoring.""",
    tools=[read_scada_telemetry]
)

vibration_analyzer = Agent(
    name="VibrationAnalyzer",
    instructions="""You are a vibration analysis expert for rotating machinery.
    Analyze vibration patterns to detect early signs of mechanical failure.
    Use FFT analysis and pattern recognition for fault diagnosis.
    SLA: Complete analysis within 5 seconds per turbine.""",
    tools=[analyze_vibration_patterns]
)

power_forecaster = Agent(
    name="PowerForecaster",
    instructions="""You are a power generation forecasting specialist.
    Predict power output based on weather forecasts and historical patterns.
    Consider grid demand and optimize generation schedules.
    SLA: Generate 24-hour forecast within 30 seconds.""",
    tools=[forecast_power_generation]
)

maintenance_scheduler = Agent(
    name="MaintenanceScheduler",
    instructions="""You are a predictive maintenance planning expert.
    Schedule maintenance based on condition monitoring and failure predictions.
    Minimize production loss while ensuring turbine reliability.
    SLA: Create maintenance plan within 1 minute.""",
    tools=[schedule_maintenance]
)


# Energy workflow with grid integration
def energy_monitoring_workflow(turbine_ids: List[str], weather_forecast: Dict):
    """
    Complete energy monitoring and optimization workflow
    Includes predictive maintenance and grid integration
    """
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "turbines_monitored": len(turbine_ids),
        "alerts": [],
        "maintenance_required": [],
        "power_forecast": None
    }
    
    # Step 1: Monitor all turbines
    for turbine_id in turbine_ids:
        try:
            # Read SCADA data
            scada_data = scada_reader.start(
                f"Read telemetry for turbine {turbine_id}"
            )
            
            # Analyze vibrations
            vibration_result = vibration_analyzer.start(
                f"Analyze vibrations for data: {scada_data}"
            )
            
            # Check for anomalies
            if vibration_result.get("anomaly_detected"):
                results["alerts"].append({
                    "turbine_id": turbine_id,
                    "type": "vibration_anomaly",
                    "severity": "high" if vibration_result.get("failure_probability", 0) > 0.7 else "medium"
                })
                
                # Schedule maintenance if needed
                maintenance_plan = maintenance_scheduler.start(
                    f"Schedule maintenance for turbine {turbine_id} with urgency based on {vibration_result}"
                )
                results["maintenance_required"].append(maintenance_plan)
                
        except Exception as e:
            # Fallback: Mark turbine for manual inspection
            results["alerts"].append({
                "turbine_id": turbine_id,
                "type": "monitoring_failure",
                "error": str(e),
                "action": "manual_inspection_required"
            })
    
    # Step 2: Power generation forecast
    try:
        historical_data = []  # Would be fetched from database
        power_forecast = power_forecaster.start(
            f"Forecast power with weather {weather_forecast} and history {historical_data}"
        )
        results["power_forecast"] = power_forecast
        
        # Grid integration check
        if power_forecast.get("predicted_output"):
            total_predicted = sum(power_forecast["predicted_output"])
            grid_demand = power_forecast.get("grid_demand", 0)
            
            if total_predicted < grid_demand * 0.9:
                results["alerts"].append({
                    "type": "supply_shortage",
                    "predicted": total_predicted,
                    "demand": grid_demand,
                    "action": "consider_backup_sources"
                })
                
    except Exception as e:
        # Fallback: Use conservative forecast
        results["power_forecast"] = {
            "status": "fallback_mode",
            "conservative_estimate": len(turbine_ids) * 1.5,  # MW
            "error": str(e)
        }
    
    return results


# Cross-industry pattern adaptation
class EnergyPatternAdapter:
    """
    Adapts manufacturing patterns for energy sector
    Demonstrates 70% code reuse across industries
    """
    
    @staticmethod
    def adapt_for_solar_farm():
        """Adapt wind farm agents for solar farm monitoring"""
        return Agent(
            name="SolarMonitor",
            instructions="""Monitor solar panel efficiency and temperature.
            Track irradiance levels and predict power output.
            Detect panel degradation and soiling issues.
            SLA: Real-time monitoring with 2-second updates."""
        )
    
    @staticmethod
    def adapt_for_power_grid():
        """Adapt for power grid management"""
        return Agent(
            name="GridBalancer",
            instructions="""Balance power supply and demand across the grid.
            Manage load distribution and prevent blackouts.
            Coordinate with renewable and traditional sources.
            SLA: Sub-second response for grid stability."""
        )
    
    @staticmethod
    def adapt_for_battery_storage():
        """Adapt for battery energy storage systems"""
        return Agent(
            name="BatteryOptimizer",
            instructions="""Optimize battery charge/discharge cycles.
            Predict battery degradation and schedule replacements.
            Maximize energy arbitrage opportunities.
            SLA: Optimization decision within 10 seconds."""
        )


# Fallback strategies for critical operations
class EnergyFallbackStrategies:
    """
    Fallback strategies for maintaining grid stability
    """
    
    @staticmethod
    def turbine_failure_fallback(failed_turbine_id: str, available_turbines: List[str]):
        """Handle turbine failure by redistributing load"""
        return {
            "strategy": "load_redistribution",
            "failed_turbine": failed_turbine_id,
            "compensating_turbines": available_turbines[:3],  # Use top 3 turbines
            "increase_output_by": 0.3,  # MW per turbine
            "duration": "until_maintenance_complete"
        }
    
    @staticmethod
    def forecast_failure_fallback(last_known_forecast: Optional[Dict]):
        """Handle forecasting system failure"""
        if last_known_forecast:
            return {
                "strategy": "use_last_known",
                "forecast": last_known_forecast,
                "confidence": 0.6,
                "validity": "4_hours"
            }
        else:
            return {
                "strategy": "seasonal_average",
                "estimated_output": 50.0,  # MW based on seasonal average
                "confidence": 0.4,
                "recommendation": "increase_reserves"
            }
    
    @staticmethod
    def communication_failure_fallback():
        """Handle SCADA communication failure"""
        return {
            "strategy": "local_control_mode",
            "actions": [
                "Switch turbines to autonomous mode",
                "Use local safety thresholds",
                "Log data locally for later sync",
                "Alert maintenance teams"
            ],
            "recovery_check_interval": 300  # seconds
        }


# Example usage
if __name__ == "__main__":
    # Monitor wind farm
    turbine_list = [f"WT-{i:03d}" for i in range(1, 11)]  # 10 turbines
    weather = {"wind_speed": 14.0, "direction": "NW", "temperature": 15.0}
    
    result = energy_monitoring_workflow(turbine_list, weather)
    print("Energy monitoring result:", result)
    
    # Demonstrate cross-industry adaptation
    solar_monitor = EnergyPatternAdapter.adapt_for_solar_farm()
    grid_balancer = EnergyPatternAdapter.adapt_for_power_grid()
    battery_optimizer = EnergyPatternAdapter.adapt_for_battery_storage()
    
    # Fallback examples
    turbine_fallback = EnergyFallbackStrategies.turbine_failure_fallback(
        "WT-003", ["WT-001", "WT-002", "WT-004", "WT-005"]
    )
    print("Turbine failure fallback:", turbine_fallback)