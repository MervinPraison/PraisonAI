"""
Healthcare Industry Template
============================
Emergency triage and patient care coordination workflow
Based on SRAO Framework with HIPAA-compliant patterns

Key agents:
- VitalSignsCapture: Processes patient vital signs
- EMRRetrieval: Retrieves electronic medical records
- TriageRecommendation: Provides triage recommendations
- ResourceAllocator: Manages hospital resource allocation
"""

from praisonaiagents import Agent, tool
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from datetime import datetime
from enum import Enum


# Triage levels following Emergency Severity Index (ESI)
class TriageLevel(str, Enum):
    RESUSCITATION = "1_resuscitation"  # Immediate life-saving intervention
    EMERGENT = "2_emergent"  # High risk, severe pain/distress
    URGENT = "3_urgent"  # Stable but needs multiple resources
    LESS_URGENT = "4_less_urgent"  # Stable, one resource needed
    NON_URGENT = "5_non_urgent"  # Stable, no resources needed


# I/O Schemas
class VitalSigns(BaseModel):
    """Patient vital signs data"""
    patient_id: str
    timestamp: str
    heart_rate: int  # bpm
    blood_pressure_systolic: int  # mmHg
    blood_pressure_diastolic: int  # mmHg
    respiratory_rate: int  # breaths/min
    temperature: float  # Celsius
    oxygen_saturation: int  # percentage
    pain_scale: int  # 0-10
    consciousness_level: str  # alert, verbal, pain, unresponsive (AVPU)


class MedicalHistory(BaseModel):
    """Patient medical history from EMR"""
    patient_id: str
    allergies: List[str]
    chronic_conditions: List[str]
    current_medications: List[Dict[str, str]]
    recent_visits: List[Dict[str, Any]]
    emergency_contacts: List[Dict[str, str]]
    insurance_status: str


class TriageAssessment(BaseModel):
    """Triage assessment and recommendations"""
    assessment_id: str
    patient_id: str
    triage_level: TriageLevel
    chief_complaint: str
    recommended_department: str
    estimated_wait_time: int  # minutes
    required_resources: List[str]
    clinical_notes: str
    red_flags: List[str]


class ResourceAllocation(BaseModel):
    """Hospital resource allocation"""
    allocation_id: str
    patient_id: str
    assigned_bed: Optional[str]
    assigned_staff: List[str]
    equipment_needed: List[str]
    department: str
    priority_score: float
    estimated_treatment_time: int  # minutes


# Healthcare-specific tools
@tool
def capture_vital_signs(patient_id: str) -> Dict:
    """Capture patient vital signs from monitoring devices"""
    # Simulate vital signs capture
    return {
        "patient_id": patient_id,
        "timestamp": datetime.now().isoformat(),
        "heart_rate": 78,
        "blood_pressure_systolic": 130,
        "blood_pressure_diastolic": 85,
        "respiratory_rate": 16,
        "temperature": 37.2,
        "oxygen_saturation": 98,
        "pain_scale": 6,
        "consciousness_level": "alert"
    }


@tool
def retrieve_medical_history(patient_id: str, consent_verified: bool = True) -> Dict:
    """Retrieve patient medical history from EMR system"""
    if not consent_verified:
        return {"error": "consent_required", "message": "Patient consent required for EMR access"}
    
    # Simulate EMR retrieval
    return {
        "patient_id": patient_id,
        "allergies": ["penicillin", "latex"],
        "chronic_conditions": ["hypertension", "diabetes_type2"],
        "current_medications": [
            {"name": "metformin", "dose": "500mg", "frequency": "twice daily"},
            {"name": "lisinopril", "dose": "10mg", "frequency": "once daily"}
        ],
        "recent_visits": [
            {"date": "2024-02-15", "reason": "routine_checkup", "department": "primary_care"}
        ],
        "emergency_contacts": [
            {"name": "Jane Doe", "relationship": "spouse", "phone": "555-0123"}
        ],
        "insurance_status": "active"
    }


@tool
def calculate_triage_priority(vital_signs: Dict, medical_history: Dict, chief_complaint: str) -> Dict:
    """Calculate triage priority based on clinical indicators"""
    # Simulate triage algorithm
    priority_score = 0
    red_flags = []
    
    # Check vital signs
    if vital_signs["heart_rate"] > 120 or vital_signs["heart_rate"] < 50:
        priority_score += 3
        red_flags.append("abnormal_heart_rate")
    
    if vital_signs["oxygen_saturation"] < 92:
        priority_score += 4
        red_flags.append("low_oxygen")
    
    if vital_signs["consciousness_level"] != "alert":
        priority_score += 5
        red_flags.append("altered_consciousness")
    
    # Determine triage level
    if priority_score >= 8:
        triage_level = TriageLevel.RESUSCITATION
        department = "emergency"
        wait_time = 0
    elif priority_score >= 5:
        triage_level = TriageLevel.EMERGENT
        department = "emergency"
        wait_time = 10
    elif priority_score >= 3:
        triage_level = TriageLevel.URGENT
        department = "urgent_care"
        wait_time = 30
    else:
        triage_level = TriageLevel.LESS_URGENT
        department = "primary_care"
        wait_time = 60
    
    return {
        "assessment_id": f"TRG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "patient_id": vital_signs["patient_id"],
        "triage_level": triage_level.value,
        "chief_complaint": chief_complaint,
        "recommended_department": department,
        "estimated_wait_time": wait_time,
        "required_resources": ["physician", "nurse", "monitoring"],
        "clinical_notes": f"Priority score: {priority_score}",
        "red_flags": red_flags
    }


@tool
def allocate_resources(patient_id: str, triage_level: str, department: str) -> Dict:
    """Allocate hospital resources based on triage assessment"""
    # Simulate resource allocation
    if "resuscitation" in triage_level:
        bed = "ER-01"
        staff = ["Dr. Smith", "Nurse Johnson", "Nurse Williams"]
        equipment = ["cardiac_monitor", "defibrillator", "crash_cart"]
        priority = 10.0
    elif "emergent" in triage_level:
        bed = "ER-05"
        staff = ["Dr. Brown", "Nurse Davis"]
        equipment = ["vital_signs_monitor", "IV_pump"]
        priority = 8.0
    else:
        bed = "UC-12"
        staff = ["PA Miller", "Nurse Garcia"]
        equipment = ["basic_monitor"]
        priority = 5.0
    
    return {
        "allocation_id": f"RES-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "patient_id": patient_id,
        "assigned_bed": bed,
        "assigned_staff": staff,
        "equipment_needed": equipment,
        "department": department,
        "priority_score": priority,
        "estimated_treatment_time": 45
    }


# Healthcare agent definitions with SLA requirements
vital_signs_agent = Agent(
    name="VitalSignsCapture",
    instructions="""You are a clinical vital signs specialist.
    Capture and interpret patient vital signs from various monitoring devices.
    Identify abnormal values and trends that require immediate attention.
    Follow HIPAA guidelines for patient data handling.
    SLA: Capture and process within 30 seconds.""",
    tools=[capture_vital_signs]
)

emr_agent = Agent(
    name="EMRRetrieval",
    instructions="""You are an EMR system specialist with HIPAA compliance expertise.
    Retrieve relevant patient medical history while ensuring data privacy.
    Verify patient consent and maintain audit trails.
    Highlight relevant allergies and contraindications.
    SLA: Retrieve records within 5 seconds.""",
    tools=[retrieve_medical_history]
)

triage_agent = Agent(
    name="TriageRecommendation",
    instructions="""You are an emergency triage specialist following ESI guidelines.
    Assess patient severity and provide triage recommendations.
    Consider vital signs, medical history, and presenting symptoms.
    Identify red flags that require immediate intervention.
    SLA: Complete assessment within 1 minute.""",
    tools=[calculate_triage_priority]
)

resource_agent = Agent(
    name="ResourceAllocator",
    instructions="""You are a hospital resource management specialist.
    Allocate beds, staff, and equipment based on patient needs and priority.
    Optimize resource utilization while maintaining quality of care.
    Coordinate between departments for efficient patient flow.
    SLA: Allocate resources within 30 seconds.""",
    tools=[allocate_resources]
)


# Healthcare workflow with safety protocols
def emergency_triage_workflow(patient_id: str, chief_complaint: str):
    """
    Complete emergency triage workflow from arrival to resource allocation
    Includes safety checks and fallback protocols
    """
    
    workflow_result = {
        "patient_id": patient_id,
        "timestamp": datetime.now().isoformat(),
        "status": "in_progress",
        "safety_checks": [],
        "clinical_pathway": []
    }
    
    # Step 1: Vital signs capture with validation
    try:
        vital_signs = vital_signs_agent.start(
            f"Capture vital signs for patient {patient_id}"
        )
        workflow_result["clinical_pathway"].append({
            "step": "vital_signs",
            "status": "completed",
            "data": vital_signs
        })
        
        # Safety check: Validate vital signs are within possible ranges
        if vital_signs.get("heart_rate", 0) < 20 or vital_signs.get("heart_rate", 0) > 300:
            workflow_result["safety_checks"].append({
                "type": "vital_signs_validation",
                "issue": "impossible_heart_rate",
                "action": "manual_verification_required"
            })
    except Exception as e:
        # Fallback: Manual vital signs entry
        workflow_result["clinical_pathway"].append({
            "step": "vital_signs",
            "status": "manual_entry_required",
            "error": str(e)
        })
        vital_signs = {"manual_entry": True}
    
    # Step 2: EMR retrieval with consent check
    try:
        medical_history = emr_agent.start(
            f"Retrieve medical history for patient {patient_id} with verified consent"
        )
        workflow_result["clinical_pathway"].append({
            "step": "emr_retrieval",
            "status": "completed",
            "records_retrieved": True
        })
        
        # Safety check: Allergy alerts
        if medical_history.get("allergies"):
            workflow_result["safety_checks"].append({
                "type": "allergy_alert",
                "allergies": medical_history["allergies"],
                "action": "notify_all_providers"
            })
    except Exception as e:
        # Fallback: Proceed with limited information
        medical_history = {
            "patient_id": patient_id,
            "allergies": [],
            "note": "EMR_unavailable_proceed_with_caution"
        }
        workflow_result["safety_checks"].append({
            "type": "emr_unavailable",
            "action": "collect_history_manually"
        })
    
    # Step 3: Triage assessment
    try:
        triage_assessment = triage_agent.start(
            f"Assess triage for patient with vitals {vital_signs}, "
            f"history {medical_history}, complaint: {chief_complaint}"
        )
        workflow_result["clinical_pathway"].append({
            "step": "triage_assessment",
            "status": "completed",
            "triage_level": triage_assessment.get("triage_level")
        })
        
        # Safety check: Red flags requiring immediate action
        if triage_assessment.get("red_flags"):
            workflow_result["safety_checks"].append({
                "type": "clinical_red_flags",
                "flags": triage_assessment["red_flags"],
                "action": "immediate_physician_notification"
            })
    except Exception as e:
        # Fallback: Conservative triage (assume urgent)
        triage_assessment = {
            "triage_level": TriageLevel.URGENT.value,
            "recommended_department": "emergency",
            "fallback": True
        }
    
    # Step 4: Resource allocation
    try:
        resource_allocation = resource_agent.start(
            f"Allocate resources for patient {patient_id} "
            f"with triage {triage_assessment.get('triage_level')} "
            f"to {triage_assessment.get('recommended_department')}"
        )
        workflow_result["clinical_pathway"].append({
            "step": "resource_allocation",
            "status": "completed",
            "bed_assigned": resource_allocation.get("assigned_bed"),
            "staff_assigned": resource_allocation.get("assigned_staff")
        })
    except Exception as e:
        # Fallback: Queue for next available
        workflow_result["clinical_pathway"].append({
            "step": "resource_allocation",
            "status": "queued",
            "queue_position": "next_available",
            "error": str(e)
        })
    
    workflow_result["status"] = "completed"
    return workflow_result


# HIPAA-compliant data handling patterns
class HIPAACompliancePatterns:
    """
    Reusable patterns for HIPAA-compliant healthcare workflows
    """
    
    @staticmethod
    def anonymize_patient_data(data: Dict) -> Dict:
        """Remove PHI for analytics and reporting"""
        safe_fields = ["triage_level", "department", "wait_time", "resource_type"]
        return {k: v for k, v in data.items() if k in safe_fields}
    
    @staticmethod
    def audit_log_access(user_id: str, patient_id: str, action: str, reason: str):
        """Create audit trail for EMR access"""
        return {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "patient_id": patient_id,
            "action": action,
            "reason": reason,
            "ip_address": "10.0.0.1",  # Would be actual IP
            "session_id": "SEC-" + datetime.now().strftime('%Y%m%d%H%M%S')
        }
    
    @staticmethod
    def encrypt_sensitive_data(data: Dict) -> Dict:
        """Encrypt sensitive fields (placeholder for real encryption)"""
        sensitive_fields = ["ssn", "dob", "address", "phone"]
        encrypted = data.copy()
        for field in sensitive_fields:
            if field in encrypted:
                encrypted[field] = f"ENCRYPTED_{field.upper()}"
        return encrypted


# Cross-department coordination patterns
class HealthcareCoordinationPatterns:
    """
    Patterns for coordinating across healthcare departments
    """
    
    @staticmethod
    def coordinate_lab_orders(patient_id: str, triage_level: str) -> Agent:
        """Create agent for lab order coordination"""
        return Agent(
            name="LabCoordinator",
            instructions=f"""Coordinate laboratory orders for patient {patient_id}.
            Priority level: {triage_level}.
            Ensure STAT orders for critical patients.
            Track specimen collection and result delivery.
            SLA: Order placement within 2 minutes."""
        )
    
    @staticmethod
    def coordinate_radiology(patient_id: str, imaging_type: str) -> Agent:
        """Create agent for radiology coordination"""
        return Agent(
            name="RadiologyCoordinator",
            instructions=f"""Schedule {imaging_type} imaging for patient {patient_id}.
            Check for contrast allergies and pregnancy status.
            Coordinate with transport for patient movement.
            SLA: Schedule within 5 minutes for urgent cases."""
        )
    
    @staticmethod
    def coordinate_pharmacy(patient_id: str, medications: List[str]) -> Agent:
        """Create agent for pharmacy coordination"""
        return Agent(
            name="PharmacyCoordinator",
            instructions=f"""Verify and dispense medications for patient {patient_id}.
            Check for drug interactions and allergies.
            Ensure proper dosing based on patient parameters.
            SLA: Medication verification within 3 minutes."""
        )


# Example usage
if __name__ == "__main__":
    # Process emergency patient
    patient_id = "PT-2024-00123"
    chief_complaint = "severe chest pain radiating to left arm"
    
    result = emergency_triage_workflow(patient_id, chief_complaint)
    print("Triage workflow result:", result)
    
    # Create specialized coordinators
    lab_coordinator = HealthcareCoordinationPatterns.coordinate_lab_orders(
        patient_id, TriageLevel.EMERGENT.value
    )
    
    radiology_coordinator = HealthcareCoordinationPatterns.coordinate_radiology(
        patient_id, "chest_xray"
    )
    
    pharmacy_coordinator = HealthcareCoordinationPatterns.coordinate_pharmacy(
        patient_id, ["aspirin", "nitroglycerin"]
    )
    
    # HIPAA compliance example
    audit_log = HIPAACompliancePatterns.audit_log_access(
        "DR-001", patient_id, "EMR_ACCESS", "emergency_triage"
    )
    print("Audit log created:", audit_log)