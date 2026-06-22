"""
Agriculture Industry Template
=============================
Precision agriculture and pest management workflow
Based on SRAO Framework with IoT sensor integration

Key agents:
- MultispectralAnalyzer: Analyzes multispectral imagery
- DiseaseIdentifier: Identifies crop diseases and pests
- SprayRecommender: Recommends targeted spraying strategies
- YieldPredictor: Predicts crop yield based on conditions
"""

from praisonaiagents import Agent, tool
from typing import Dict, List, Any, Tuple
from pydantic import BaseModel
from datetime import datetime, timedelta
from enum import Enum


# Crop health levels
class CropHealthLevel(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


# Pest/Disease severity
class SeverityLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"


# I/O Schemas
class MultispectralData(BaseModel):
    """Multispectral imagery analysis data"""
    field_id: str
    capture_time: str
    ndvi_index: float  # Normalized Difference Vegetation Index
    ndre_index: float  # Normalized Difference Red Edge
    ccci_index: float  # Canopy Chlorophyll Content Index
    moisture_level: float  # Soil moisture percentage
    temperature: float  # Celsius
    affected_area: float  # Hectares
    gps_coordinates: Tuple[float, float]


class PestDiseaseReport(BaseModel):
    """Pest and disease identification report"""
    report_id: str
    field_id: str
    detection_time: str
    pest_type: Optional[str]
    disease_type: Optional[str]
    severity: SeverityLevel
    affected_crops: List[str]
    spread_rate: float  # % per day
    environmental_factors: Dict[str, Any]
    confidence_score: float


class SprayRecommendation(BaseModel):
    """Targeted spraying recommendation"""
    recommendation_id: str
    field_id: str
    treatment_type: str  # pesticide, fungicide, herbicide, fertilizer
    product_name: str
    application_rate: float  # L/hectare
    target_zones: List[Dict[str, Any]]  # GPS zones
    optimal_time: str
    weather_window: Dict[str, Any]
    cost_estimate: float
    environmental_impact: str  # low, medium, high


class YieldForecast(BaseModel):
    """Crop yield prediction"""
    forecast_id: str
    field_id: str
    crop_type: str
    predicted_yield: float  # tons/hectare
    confidence_interval: Tuple[float, float]
    harvest_window: Tuple[str, str]
    quality_grade: str  # A, B, C
    market_price_estimate: float
    risk_factors: List[str]


# Agriculture-specific tools
@tool
def analyze_multispectral_imagery(field_id: str, image_data: Dict) -> Dict:
    """Analyze multispectral drone/satellite imagery for crop health"""
    # Simulate multispectral analysis
    ndvi = 0.75  # Healthy vegetation typically 0.6-0.9
    
    # Determine health based on NDVI
    if ndvi > 0.8:
        health = CropHealthLevel.EXCELLENT
        affected_area = 0.0
    elif ndvi > 0.6:
        health = CropHealthLevel.GOOD
        affected_area = 2.5
    elif ndvi > 0.4:
        health = CropHealthLevel.FAIR
        affected_area = 5.0
    else:
        health = CropHealthLevel.POOR
        affected_area = 10.0
    
    return {
        "field_id": field_id,
        "capture_time": datetime.now().isoformat(),
        "ndvi_index": ndvi,
        "ndre_index": 0.68,
        "ccci_index": 0.72,
        "moisture_level": 35.0,
        "temperature": 24.5,
        "affected_area": affected_area,
        "gps_coordinates": (40.7128, -74.0060),
        "health_level": health.value
    }


@tool
def identify_pest_disease(spectral_data: Dict, historical_data: List) -> Dict:
    """Identify pests and diseases using AI image recognition"""
    # Simulate pest/disease detection
    ndvi = spectral_data.get("ndvi_index", 0.75)
    affected_area = spectral_data.get("affected_area", 0)
    
    if affected_area > 8.0:
        pest_type = "aphids"
        disease_type = "powdery_mildew"
        severity = SeverityLevel.HIGH
        spread_rate = 2.5
    elif affected_area > 4.0:
        pest_type = "whiteflies"
        disease_type = "leaf_spot"
        severity = SeverityLevel.MODERATE
        spread_rate = 1.5
    elif affected_area > 0:
        pest_type = None
        disease_type = "early_blight"
        severity = SeverityLevel.LOW
        spread_rate = 0.5
    else:
        pest_type = None
        disease_type = None
        severity = SeverityLevel.NONE
        spread_rate = 0.0
    
    return {
        "report_id": f"PDR-{datetime.now().strftime('%Y%m%d%H%M')}",
        "field_id": spectral_data["field_id"],
        "detection_time": datetime.now().isoformat(),
        "pest_type": pest_type,
        "disease_type": disease_type,
        "severity": severity.value,
        "affected_crops": ["wheat", "corn"],
        "spread_rate": spread_rate,
        "environmental_factors": {
            "humidity": 65,
            "temperature": spectral_data.get("temperature", 25),
            "rainfall_last_week": 15  # mm
        },
        "confidence_score": 0.85
    }


@tool
def calculate_spray_recommendation(pest_report: Dict, field_data: Dict, weather: Dict) -> Dict:
    """Calculate optimal spraying strategy for pest/disease control"""
    severity = pest_report.get("severity", "none")
    
    if severity == "high" or severity == "severe":
        treatment = "pesticide"
        product = "Imidacloprid"
        rate = 0.5
        impact = "medium"
    elif severity == "moderate":
        treatment = "fungicide"
        product = "Azoxystrobin"
        rate = 0.3
        impact = "low"
    elif severity == "low":
        treatment = "organic_treatment"
        product = "Neem Oil"
        rate = 0.2
        impact = "minimal"
    else:
        treatment = "fertilizer"
        product = "NPK 20-20-20"
        rate = 0.4
        impact = "positive"
    
    # Calculate target zones based on affected area
    affected_area = field_data.get("affected_area", 0)
    if affected_area > 0:
        target_zones = [
            {
                "zone_id": "A1",
                "gps_boundary": [(40.71, -74.00), (40.72, -74.01)],
                "priority": "high"
            }
        ]
    else:
        target_zones = []
    
    return {
        "recommendation_id": f"SPR-{datetime.now().strftime('%Y%m%d%H%M')}",
        "field_id": field_data["field_id"],
        "treatment_type": treatment,
        "product_name": product,
        "application_rate": rate,
        "target_zones": target_zones,
        "optimal_time": (datetime.now() + timedelta(days=1)).isoformat(),
        "weather_window": {
            "wind_speed": weather.get("wind_speed", 5),
            "precipitation": weather.get("precipitation", 0),
            "suitable": True
        },
        "cost_estimate": rate * affected_area * 50,  # $/hectare
        "environmental_impact": impact
    }


@tool
def predict_crop_yield(field_id: str, crop_type: str, current_health: Dict, weather_forecast: Dict) -> Dict:
    """Predict crop yield based on current conditions and forecasts"""
    # Simulate yield prediction
    health_level = current_health.get("health_level", "good")
    
    base_yield = {
        "wheat": 3.5,
        "corn": 9.5,
        "soybeans": 2.8,
        "rice": 6.0
    }.get(crop_type, 5.0)
    
    # Adjust based on health
    health_multiplier = {
        "excellent": 1.2,
        "good": 1.0,
        "fair": 0.8,
        "poor": 0.6,
        "critical": 0.4
    }.get(health_level, 1.0)
    
    predicted_yield = base_yield * health_multiplier
    
    # Quality grade based on conditions
    if health_level in ["excellent", "good"]:
        quality = "A"
        price_multiplier = 1.2
    elif health_level == "fair":
        quality = "B"
        price_multiplier = 1.0
    else:
        quality = "C"
        price_multiplier = 0.8
    
    return {
        "forecast_id": f"YLD-{datetime.now().strftime('%Y%m%d%H%M')}",
        "field_id": field_id,
        "crop_type": crop_type,
        "predicted_yield": predicted_yield,
        "confidence_interval": (predicted_yield * 0.9, predicted_yield * 1.1),
        "harvest_window": (
            (datetime.now() + timedelta(days=60)).isoformat(),
            (datetime.now() + timedelta(days=75)).isoformat()
        ),
        "quality_grade": quality,
        "market_price_estimate": predicted_yield * 250 * price_multiplier,  # $/ton
        "risk_factors": ["weather_variability", "pest_pressure", "market_volatility"]
    }


# Agriculture agent definitions
multispectral_agent = Agent(
    name="MultispectralAnalyzer",
    instructions="""You are a remote sensing specialist for precision agriculture.
    Analyze multispectral imagery from drones and satellites.
    Calculate vegetation indices (NDVI, NDRE, CCCI) to assess crop health.
    Identify stress zones and anomalies in field conditions.
    SLA: Process imagery within 2 minutes per field.""",
    tools=[analyze_multispectral_imagery]
)

disease_agent = Agent(
    name="DiseaseIdentifier",
    instructions="""You are a plant pathology expert with AI vision capabilities.
    Identify crop diseases, pests, and nutrient deficiencies.
    Assess severity levels and predict spread patterns.
    Consider environmental factors affecting disease development.
    SLA: Complete identification within 30 seconds.""",
    tools=[identify_pest_disease]
)

spray_agent = Agent(
    name="SprayRecommender",
    instructions="""You are a precision application specialist.
    Recommend targeted spraying strategies for pest and disease control.
    Optimize chemical usage to minimize environmental impact.
    Consider weather windows and application regulations.
    SLA: Generate recommendations within 1 minute.""",
    tools=[calculate_spray_recommendation]
)

yield_agent = Agent(
    name="YieldPredictor",
    instructions="""You are a crop yield forecasting specialist.
    Predict harvest yields based on current conditions and historical data.
    Assess crop quality grades and market value estimates.
    Identify risk factors that could impact final yield.
    SLA: Generate forecast within 45 seconds.""",
    tools=[predict_crop_yield]
)


# Precision agriculture workflow
def precision_agriculture_workflow(field_ids: List[str], crop_type: str, weather_data: Dict):
    """
    Complete precision agriculture workflow from monitoring to treatment
    Includes early warning system and sustainable farming practices
    """
    
    workflow_results = {
        "timestamp": datetime.now().isoformat(),
        "fields_monitored": len(field_ids),
        "alerts": [],
        "treatments_needed": [],
        "yield_forecasts": [],
        "sustainability_score": 0.0
    }
    
    for field_id in field_ids:
        try:
            # Step 1: Multispectral analysis
            spectral_analysis = multispectral_agent.start(
                f"Analyze multispectral imagery for field {field_id}"
            )
            
            # Step 2: Disease and pest detection
            pest_report = disease_agent.start(
                f"Identify pests/diseases from spectral data: {spectral_analysis}"
            )
            
            # Check for alerts
            if pest_report.get("severity") in ["high", "severe"]:
                workflow_results["alerts"].append({
                    "field_id": field_id,
                    "type": "pest_disease_alert",
                    "severity": pest_report["severity"],
                    "pest": pest_report.get("pest_type"),
                    "disease": pest_report.get("disease_type"),
                    "action": "immediate_treatment_required"
                })
                
                # Step 3: Generate spray recommendation
                spray_recommendation = spray_agent.start(
                    f"Calculate spray strategy for pest report: {pest_report}, "
                    f"field: {spectral_analysis}, weather: {weather_data}"
                )
                workflow_results["treatments_needed"].append(spray_recommendation)
            
            # Step 4: Yield prediction
            yield_forecast = yield_agent.start(
                f"Predict yield for field {field_id}, crop {crop_type}, "
                f"health: {spectral_analysis}, weather: {weather_data}"
            )
            workflow_results["yield_forecasts"].append(yield_forecast)
            
        except Exception as e:
            # Fallback: Schedule manual inspection
            workflow_results["alerts"].append({
                "field_id": field_id,
                "type": "monitoring_failure",
                "error": str(e),
                "action": "schedule_manual_inspection"
            })
    
    # Calculate sustainability score
    total_chemical = sum(
        t.get("application_rate", 0) * t.get("affected_area", 0) 
        for t in workflow_results["treatments_needed"]
    )
    workflow_results["sustainability_score"] = max(0, 100 - (total_chemical * 10))
    
    return workflow_results


# Sustainable farming patterns
class SustainableFarmingPatterns:
    """
    Patterns for sustainable and regenerative agriculture
    """
    
    @staticmethod
    def integrated_pest_management(pest_level: str) -> Dict:
        """IPM strategy based on pest pressure"""
        strategies = {
            "low": {
                "method": "biological_control",
                "actions": ["release_beneficial_insects", "plant_trap_crops"],
                "chemical_use": 0
            },
            "moderate": {
                "method": "targeted_intervention",
                "actions": ["spot_treatment", "pheromone_traps", "minimal_spray"],
                "chemical_use": 30
            },
            "high": {
                "method": "integrated_approach",
                "actions": ["systematic_spray", "crop_rotation", "resistant_varieties"],
                "chemical_use": 70
            }
        }
        return strategies.get(pest_level, strategies["moderate"])
    
    @staticmethod
    def precision_irrigation(moisture_level: float, crop_stage: str) -> Dict:
        """Calculate optimal irrigation based on soil moisture and crop stage"""
        # Water requirements by growth stage (mm/day)
        stage_requirements = {
            "germination": 3.0,
            "vegetative": 5.0,
            "flowering": 7.0,
            "grain_filling": 6.0,
            "maturation": 2.0
        }
        
        required = stage_requirements.get(crop_stage, 5.0)
        deficit = max(0, 40 - moisture_level)  # Target 40% moisture
        
        return {
            "irrigation_needed": deficit > 10,
            "amount_mm": deficit * 2,
            "method": "drip" if deficit < 20 else "sprinkler",
            "schedule": "night_irrigation" if deficit > 15 else "morning_irrigation",
            "water_saved": (100 - deficit) / 100 * 1000  # Liters per hectare
        }
    
    @staticmethod
    def crop_rotation_optimizer(current_crop: str, soil_data: Dict) -> str:
        """Recommend next crop for rotation based on soil health"""
        rotations = {
            "wheat": ["soybeans", "canola"],  # Nitrogen fixation
            "corn": ["soybeans", "alfalfa"],  # Break disease cycle
            "soybeans": ["wheat", "corn"],  # Utilize fixed nitrogen
            "rice": ["legumes", "vegetables"],  # Soil structure improvement
        }
        
        return rotations.get(current_crop, ["cover_crops"])[0]


# IoT sensor integration patterns
class IoTSensorPatterns:
    """
    Patterns for integrating IoT sensors in smart farming
    """
    
    @staticmethod
    def create_sensor_network_agent(sensor_types: List[str]) -> Agent:
        """Create agent for managing IoT sensor networks"""
        return Agent(
            name="SensorNetworkManager",
            instructions=f"""Manage IoT sensor network with {', '.join(sensor_types)}.
            Collect real-time data from field sensors.
            Detect sensor anomalies and maintenance needs.
            Aggregate data for precision agriculture decisions.
            SLA: Data collection every 15 minutes."""
        )
    
    @staticmethod
    def process_sensor_data(sensor_readings: List[Dict]) -> Dict:
        """Process and aggregate IoT sensor data"""
        aggregated = {
            "timestamp": datetime.now().isoformat(),
            "sensor_count": len(sensor_readings),
            "averages": {},
            "alerts": []
        }
        
        # Calculate averages
        for reading in sensor_readings:
            for key, value in reading.items():
                if isinstance(value, (int, float)):
                    if key not in aggregated["averages"]:
                        aggregated["averages"][key] = []
                    aggregated["averages"][key].append(value)
        
        # Convert to means
        for key in aggregated["averages"]:
            values = aggregated["averages"][key]
            aggregated["averages"][key] = sum(values) / len(values)
            
            # Check for anomalies
            if key == "soil_ph" and (aggregated["averages"][key] < 6.0 or aggregated["averages"][key] > 7.5):
                aggregated["alerts"].append({
                    "type": "soil_ph_anomaly",
                    "value": aggregated["averages"][key],
                    "action": "adjust_soil_treatment"
                })
        
        return aggregated


# Example usage
if __name__ == "__main__":
    # Monitor multiple fields
    fields = ["FIELD-001", "FIELD-002", "FIELD-003"]
    weather = {
        "temperature": 25,
        "humidity": 60,
        "wind_speed": 8,
        "precipitation": 0,
        "forecast": "partly_cloudy"
    }
    
    result = precision_agriculture_workflow(fields, "wheat", weather)
    print("Agriculture workflow result:", result)
    
    # Sustainable farming example
    ipm_strategy = SustainableFarmingPatterns.integrated_pest_management("moderate")
    print("IPM Strategy:", ipm_strategy)
    
    irrigation_plan = SustainableFarmingPatterns.precision_irrigation(25.0, "flowering")
    print("Irrigation Plan:", irrigation_plan)
    
    next_crop = SustainableFarmingPatterns.crop_rotation_optimizer("wheat", {})
    print("Recommended next crop:", next_crop)
    
    # IoT integration example
    sensor_agent = IoTSensorPatterns.create_sensor_network_agent(
        ["soil_moisture", "temperature", "humidity", "light", "ph"]
    )
    
    sensor_data = [
        {"sensor_id": "S001", "soil_moisture": 35, "temperature": 24, "soil_ph": 6.8},
        {"sensor_id": "S002", "soil_moisture": 32, "temperature": 25, "soil_ph": 7.2},
        {"sensor_id": "S003", "soil_moisture": 38, "temperature": 23, "soil_ph": 5.8}
    ]
    
    processed_data = IoTSensorPatterns.process_sensor_data(sensor_data)
    print("Processed sensor data:", processed_data)