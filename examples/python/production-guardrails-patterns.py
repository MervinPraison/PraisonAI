"""
Production Guardrails Patterns Example

This example demonstrates comprehensive guardrail strategies for production environments
including multi-layered validation, compliance checks, and safety mechanisms.
"""

import re
import json
from typing import Dict, Any, List, Optional
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Production Guardrails Patterns Example ===\n")

# Advanced Guardrail Functions
class SecurityGuardrail:
    """Security-focused guardrails for sensitive operations"""
    
    @staticmethod
    def validate_no_sensitive_data(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prevent exposure of sensitive information"""
        sensitive_patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',  # Credit card
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',  # IP addresses
            r'\b[A-Za-z0-9]{20,}\b'  # API keys/tokens (simple heuristic)
        ]
        
        violations = []
        for pattern in sensitive_patterns:
            if re.search(pattern, response):
                violations.append(f"Potential sensitive data detected: {pattern}")
        
        if violations:
            return {
                "valid": False,
                "reason": f"Security violation: {'; '.join(violations)}",
                "action": "redact_and_retry",
                "severity": "high"
            }
        
        return {"valid": True}

class ComplianceGuardrail:
    """Compliance and regulatory guardrails"""
    
    @staticmethod
    def gdpr_compliance_check(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure GDPR compliance in responses"""
        gdpr_violations = []
        
        # Check for personal data collection without consent
        collection_indicators = ["collect personal data", "store your information", "track your activity"]
        if any(indicator in response.lower() for indicator in collection_indicators):
            if "consent" not in response.lower() and "agree" not in response.lower():
                gdpr_violations.append("Personal data collection mentioned without consent")
        
        # Check for data transfer mentions
        if "transfer data" in response.lower() or "send data" in response.lower():
            if "lawful basis" not in response.lower():
                gdpr_violations.append("Data transfer mentioned without lawful basis")
        
        if gdpr_violations:
            return {
                "valid": False,
                "reason": f"GDPR compliance issues: {'; '.join(gdpr_violations)}",
                "action": "add_compliance_notice",
                "severity": "high"
            }
        
        return {"valid": True}

    @staticmethod
    def medical_compliance_check(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure medical advice compliance (HIPAA, medical disclaimers)"""
        medical_keywords = ["diagnose", "treatment", "medication", "symptoms", "medical condition"]
        
        if any(keyword in response.lower() for keyword in medical_keywords):
            disclaimer_present = any(phrase in response.lower() for phrase in [
                "consult a healthcare professional",
                "not medical advice", 
                "see a doctor",
                "medical disclaimer"
            ])
            
            if not disclaimer_present:
                return {
                    "valid": False,
                    "reason": "Medical content requires appropriate disclaimer",
                    "action": "add_medical_disclaimer",
                    "severity": "high"
                }
        
        return {"valid": True}

class QualityGuardrail:
    """Quality and accuracy guardrails"""
    
    @staticmethod
    def factual_accuracy_check(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Basic factual accuracy validation"""
        # Check for obviously wrong facts (simplified examples)
        wrong_facts = [
            ("paris.*capital.*italy", "Paris is not the capital of Italy"),
            ("sun.*planet", "The sun is not a planet"),
            ("water.*boils.*0", "Water does not boil at 0 degrees Celsius")
        ]
        
        for pattern, error_msg in wrong_facts:
            if re.search(pattern, response.lower()):
                return {
                    "valid": False,
                    "reason": f"Factual error detected: {error_msg}",
                    "action": "fact_check_retry",
                    "severity": "medium"
                }
        
        return {"valid": True}
    
    @staticmethod
    def completeness_check(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure response completeness and adequacy"""
        min_length = context.get("min_response_length", 50)
        required_elements = context.get("required_elements", [])
        
        if len(response.strip()) < min_length:
            return {
                "valid": False,
                "reason": f"Response too short (< {min_length} characters)",
                "action": "expand_response",
                "severity": "low"
            }
        
        missing_elements = []
        for element in required_elements:
            if element.lower() not in response.lower():
                missing_elements.append(element)
        
        if missing_elements:
            return {
                "valid": False,
                "reason": f"Missing required elements: {', '.join(missing_elements)}",
                "action": "add_missing_elements",
                "severity": "medium"
            }
        
        return {"valid": True}

class BusinessGuardrail:
    """Business logic and policy guardrails"""
    
    @staticmethod
    def brand_safety_check(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure brand safety and appropriate tone"""
        inappropriate_content = [
            "hate speech", "discrimination", "violence", "illegal activities",
            "harmful content", "offensive language"
        ]
        
        # Simple keyword detection (in production, use more sophisticated NLP)
        violations = [content for content in inappropriate_content 
                     if any(word in response.lower() for word in content.split())]
        
        if violations:
            return {
                "valid": False,
                "reason": f"Brand safety violations: {', '.join(violations)}",
                "action": "content_filter_retry",
                "severity": "high"
            }
        
        return {"valid": True}
    
    @staticmethod
    def cost_efficiency_check(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Monitor cost efficiency and resource usage"""
        max_tokens = context.get("max_response_tokens", 1000)
        estimated_tokens = len(response.split()) * 1.3  # Rough estimate
        
        if estimated_tokens > max_tokens:
            return {
                "valid": False,
                "reason": f"Response too long ({estimated_tokens:.0f} tokens > {max_tokens})",
                "action": "truncate_response",
                "severity": "low"
            }
        
        return {"valid": True}

# Multi-layered Guardrail System
class ProductionGuardrailSystem:
    """Comprehensive guardrail system for production use"""
    
    def __init__(self):
        self.security_guardrails = [
            SecurityGuardrail.validate_no_sensitive_data
        ]
        
        self.compliance_guardrails = [
            ComplianceGuardrail.gdpr_compliance_check,
            ComplianceGuardrail.medical_compliance_check
        ]
        
        self.quality_guardrails = [
            QualityGuardrail.factual_accuracy_check,
            QualityGuardrail.completeness_check
        ]
        
        self.business_guardrails = [
            BusinessGuardrail.brand_safety_check,
            BusinessGuardrail.cost_efficiency_check
        ]
        
        self.violation_log = []
    
    def validate_response(self, response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run comprehensive guardrail validation"""
        all_guardrails = (
            self.security_guardrails + 
            self.compliance_guardrails + 
            self.quality_guardrails + 
            self.business_guardrails
        )
        
        violations = []
        highest_severity = "low"
        
        for guardrail in all_guardrails:
            try:
                result = guardrail(response, context)
                if not result.get("valid", True):
                    violations.append(result)
                    severity = result.get("severity", "low")
                    if severity == "high":
                        highest_severity = "high"
                    elif severity == "medium" and highest_severity == "low":
                        highest_severity = "medium"
            except Exception as e:
                violations.append({
                    "valid": False,
                    "reason": f"Guardrail error: {str(e)}",
                    "action": "manual_review",
                    "severity": "medium"
                })
        
        # Log violations for monitoring
        if violations:
            self.violation_log.extend(violations)
        
        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "severity": highest_severity,
            "total_violations": len(violations)
        }
    
    def get_violation_summary(self) -> Dict[str, Any]:
        """Get summary of all violations"""
        if not self.violation_log:
            return {"total_violations": 0}
        
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for violation in self.violation_log:
            severity = violation.get("severity", "low")
            severity_counts[severity] += 1
        
        return {
            "total_violations": len(self.violation_log),
            "severity_breakdown": severity_counts,
            "most_common_reasons": [v["reason"] for v in self.violation_log[:5]]
        }

# Initialize production guardrail system
guardrail_system = ProductionGuardrailSystem()

# Example 1: Secure Customer Service Agent
print("Example 1: Secure Customer Service Agent")
print("-" * 40)

def secure_customer_service_guardrail(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Custom guardrail for customer service"""
    validation = guardrail_system.validate_response(response, {
        "min_response_length": 100,
        "required_elements": ["assistance", "help"],
        "max_response_tokens": 500
    })
    
    if not validation["valid"]:
        print(f"⚠️  Guardrail violations detected: {validation['total_violations']}")
        for violation in validation["violations"]:
            print(f"   - {violation['reason']} (Action: {violation['action']})")
    
    return validation

customer_service_agent = Agent(
    name="Secure Customer Service Agent",
    role="Customer Support Specialist",
    goal="Provide helpful and secure customer support",
    backstory="Trained customer service representative with security awareness",
    instructions="""Provide helpful customer service while ensuring:
    - No sensitive customer data is exposed
    - Compliance with data protection regulations
    - Professional and brand-safe communication""",
    guardrail=secure_customer_service_guardrail,
    max_retries=3,
    verbose=True
)

customer_query = "I need help with my account that has email john.doe@example.com"
result_1 = customer_service_agent.start(customer_query)
print(f"Secure Response: {result_1[:200]}...\n")

# Example 2: Medical Information Agent with Compliance
print("Example 2: Medical Information Agent")
print("-" * 40)

def medical_compliance_guardrail(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Medical-specific guardrail with compliance checks"""
    validation = guardrail_system.validate_response(response, {
        "min_response_length": 150,
        "required_elements": ["medical professional", "disclaimer"],
        "max_response_tokens": 600
    })
    return validation

medical_agent = Agent(
    name="Medical Information Agent",
    role="Health Information Provider",
    goal="Provide helpful health information with proper disclaimers",
    backstory="Healthcare information specialist with compliance training",
    instructions="""Provide general health information while ensuring:
    - All medical advice includes appropriate disclaimers
    - Compliance with healthcare regulations
    - Clear guidance to consult healthcare professionals""",
    guardrail=medical_compliance_guardrail,
    max_retries=3,
    tools=[internet_search]
)

medical_query = "What are the symptoms of diabetes and how is it treated?"
result_2 = medical_agent.start(medical_query)
print(f"Compliant Medical Response: {result_2[:200]}...\n")

# Example 3: Financial Advisory Agent with Risk Controls
print("Example 3: Financial Advisory Agent")
print("-" * 40)

def financial_compliance_guardrail(response: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Financial advice guardrail with risk controls"""
    financial_disclaimers = [
        "not financial advice", "consult a financial advisor", "investment risk",
        "past performance", "financial professional"
    ]
    
    base_validation = guardrail_system.validate_response(response, {
        "min_response_length": 120,
        "max_response_tokens": 700
    })
    
    # Additional financial-specific checks
    if any(keyword in response.lower() for keyword in ["invest", "buy", "sell", "portfolio"]):
        disclaimer_present = any(disclaimer in response.lower() for disclaimer in financial_disclaimers)
        if not disclaimer_present:
            base_validation["violations"].append({
                "valid": False,
                "reason": "Financial advice requires appropriate disclaimer",
                "action": "add_financial_disclaimer",
                "severity": "high"
            })
            base_validation["valid"] = False
    
    return base_validation

financial_agent = Agent(
    name="Financial Information Agent",
    role="Financial Information Specialist", 
    goal="Provide financial information with proper risk disclaimers",
    backstory="Financial information specialist with regulatory compliance expertise",
    instructions="""Provide general financial information while ensuring:
    - All investment advice includes appropriate disclaimers
    - Clear risk warnings for investment products
    - Guidance to consult qualified financial advisors""",
    guardrail=financial_compliance_guardrail,
    max_retries=3,
    tools=[internet_search]
)

financial_query = "Should I invest in cryptocurrency for my retirement?"
result_3 = financial_agent.start(financial_query)
print(f"Compliant Financial Response: {result_3[:200]}...\n")

# Example 4: Multi-Agent System with Coordinated Guardrails
print("Example 4: Multi-Agent Coordinated Guardrails")
print("-" * 40)

# Research Agent with fact-checking guardrails
research_agent = Agent(
    name="Research Agent",
    role="Information Researcher",
    goal="Conduct accurate research with fact verification",
    backstory="Research specialist with emphasis on accuracy and verification",
    guardrail=lambda response, context: guardrail_system.validate_response(response, {
        "min_response_length": 200,
        "required_elements": ["source", "research"],
        "max_response_tokens": 800
    }),
    tools=[internet_search]
)

# Content Writer with brand safety guardrails
content_writer = Agent(
    name="Content Writer",
    role="Professional Content Creator",
    goal="Create brand-safe and compliant content",
    backstory="Content specialist with brand safety and compliance expertise",
    guardrail=lambda response, context: guardrail_system.validate_response(response, {
        "min_response_length": 300,
        "required_elements": ["professional", "informative"],
        "max_response_tokens": 1000
    })
)

# Create coordinated tasks
research_task = Task(
    description="Research the latest trends in renewable energy technology and their market impact",
    expected_output="Comprehensive research summary with verified facts and sources",
    agent=research_agent
)

content_task = Task(
    description="Create a professional article based on the renewable energy research",
    expected_output="Well-written, brand-safe article suitable for publication",
    agent=content_writer,
    context=[research_task]
)

# Execute with coordinated guardrails
multi_agent_system = PraisonAIAgents(
    agents=[research_agent, content_writer],
    tasks=[research_task, content_task],
    process="sequential"
)

result_4 = multi_agent_system.start()
print(f"Coordinated Guardrail Result: {result_4[:200]}...\n")

# Example 5: Guardrail Analytics and Reporting
print("Example 5: Guardrail Analytics")
print("-" * 40)

violation_summary = guardrail_system.get_violation_summary()
print(f"Total Violations Detected: {violation_summary['total_violations']}")

if violation_summary['total_violations'] > 0:
    print("Severity Breakdown:")
    for severity, count in violation_summary['severity_breakdown'].items():
        print(f"  {severity.upper()}: {count}")
    
    print("Most Common Issues:")
    for reason in violation_summary['most_common_reasons']:
        print(f"  - {reason}")

# Guardrail effectiveness metrics
print(f"\nGuardrail System Performance:")
print(f"✅ Security layer: Active")
print(f"✅ Compliance layer: Active")  
print(f"✅ Quality layer: Active")
print(f"✅ Business layer: Active")
print(f"🔍 Total checks performed: {len(guardrail_system.violation_log) + 10}")  # Approximate
print(f"📊 System reliability: {((10 - violation_summary['total_violations']) / 10 * 100):.1f}%")

print("\n=== Production Guardrails Summary ===")
print("✅ Multi-layered validation implemented")
print("✅ Compliance and regulatory checks active")
print("✅ Brand safety and security measures in place")
print("✅ Quality and completeness validation enabled")
print("✅ Real-time violation monitoring and reporting")
print("\nProduction guardrails patterns example complete!")