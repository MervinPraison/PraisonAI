"""
Production Telemetry Example

This example demonstrates comprehensive telemetry and monitoring setup for
production AI agent systems, including metrics collection, performance tracking,
and observability.

Features demonstrated:
- OpenTelemetry integration for distributed tracing
- Custom metrics collection and monitoring
- Performance tracking and analytics
- Error tracking and alerting
- Usage analytics and reporting
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo
from praisonaiagents.telemetry import enable_telemetry
import time
import random
from datetime import datetime

# Initialize telemetry for production monitoring
print("="*80)
print("PRODUCTION TELEMETRY SETUP")
print("="*80)

# Configure telemetry (in production, you'd use actual telemetry backends)
telemetry = enable_telemetry(
    backend="opentelemetry",
    config={
        "service_name": "praisonai_production_agents",
        "service_version": "1.0.0",
        "environment": "production",
        "export_console": True,  # For demo purposes
        "export_file": True,     # Export to file for analysis
        "sample_rate": 1.0,      # 100% sampling for demo
        "attributes": {
            "deployment": "cloud",
            "region": "us-east-1",
            "cluster": "main"
        }
    }
)

# Create agents for production workflow with telemetry
customer_service_agent = Agent(
    name="CustomerServiceAgent",
    role="Customer Service Representative", 
    goal="Provide excellent customer service with fast response times",
    backstory="You are a customer service representative focused on resolving customer issues quickly and effectively.",
    tools=[duckduckgo],
    instructions="Provide helpful, accurate customer service responses. Research solutions when needed."
)

technical_support_agent = Agent(
    name="TechnicalSupportAgent",
    role="Technical Support Specialist",
    goal="Resolve technical issues with detailed solutions",
    backstory="You are a technical support specialist who provides detailed technical solutions and troubleshooting.",
    instructions="Provide detailed technical solutions with step-by-step instructions."
)

quality_assurance_agent = Agent(
    name="QualityAssuranceAgent", 
    role="Quality Assurance Specialist",
    goal="Ensure all customer interactions meet quality standards",
    backstory="You review and assess the quality of customer service interactions to ensure high standards.",
    instructions="Review customer service interactions and provide quality scores with detailed feedback."
)

# Production workflow simulation with telemetry tracking
def simulate_customer_requests():
    """Simulate various customer requests for telemetry demonstration"""
    
    customer_requests = [
        {
            "type": "billing_inquiry",
            "complexity": "low",
            "description": "Customer asking about their monthly bill charges",
            "expected_duration": 30
        },
        {
            "type": "technical_issue", 
            "complexity": "high",
            "description": "Customer experiencing connectivity issues with the service",
            "expected_duration": 120
        },
        {
            "type": "account_setup",
            "complexity": "medium", 
            "description": "New customer needs help setting up their account",
            "expected_duration": 60
        },
        {
            "type": "feature_question",
            "complexity": "low",
            "description": "Customer asking about product features and capabilities",
            "expected_duration": 45
        }
    ]
    
    return customer_requests

# Execute production workflow with comprehensive telemetry
print("Starting production workflow with telemetry tracking...")

customer_requests = simulate_customer_requests()

for i, request in enumerate(customer_requests):
    print(f"\n{'='*60}")
    print(f"PROCESSING CUSTOMER REQUEST {i+1}: {request['type'].upper()}")
    print(f"Complexity: {request['complexity']} | Expected Duration: {request['expected_duration']}s")
    print(f"{'='*60}")
    
    # Start telemetry trace for this customer interaction
    with telemetry.trace_operation(f"customer_request_{request['type']}") as trace:
        
        # Add custom attributes to the trace
        trace.set_attributes({
            "request.type": request['type'],
            "request.complexity": request['complexity'],
            "request.expected_duration": request['expected_duration'],
            "customer.id": f"customer_{random.randint(1000, 9999)}",
            "agent.assigned": "CustomerServiceAgent"
        })
        
        start_time = time.time()
        
        # Create customer service task with telemetry
        customer_task = Task(
            name=f"customer_request_{i+1}",
            description=request['description'],
            expected_output="Professional customer service response with solution",
            agent=customer_service_agent
        )
        
        # Execute with telemetry tracking
        try:
            # Customer service response
            with telemetry.trace_agent_execution("CustomerServiceAgent") as agent_trace:
                agents = PraisonAIAgents(
                    agents=[customer_service_agent],
                    tasks=[customer_task],
                    verbose=False  # Reduce verbosity for telemetry demo
                )
                
                cs_result = agents.start()
                agent_trace.set_attributes({
                    "agent.response_length": len(str(cs_result)),
                    "agent.tools_used": len(customer_service_agent.tools) if customer_service_agent.tools else 0
                })
            
            # Technical support (if needed for high complexity)
            if request['complexity'] == 'high':
                with telemetry.trace_agent_execution("TechnicalSupportAgent") as tech_trace:
                    tech_task = Task(
                        name=f"technical_support_{i+1}",
                        description=f"Provide detailed technical support for: {request['description']}",
                        expected_output="Detailed technical solution with troubleshooting steps",
                        agent=technical_support_agent,
                        context=[customer_task]
                    )
                    
                    tech_agents = PraisonAIAgents(
                        agents=[technical_support_agent],
                        tasks=[tech_task],
                        verbose=False
                    )
                    
                    tech_result = tech_agents.start()
                    tech_trace.set_attributes({
                        "agent.response_length": len(str(tech_result)),
                        "agent.escalation": True
                    })
            
            # Quality assurance check
            with telemetry.trace_agent_execution("QualityAssuranceAgent") as qa_trace:
                qa_task = Task(
                    name=f"quality_check_{i+1}",
                    description=f"Review the quality of customer service provided for: {request['description']}",
                    expected_output="Quality assessment score and feedback",
                    agent=quality_assurance_agent
                )
                
                qa_agents = PraisonAIAgents(
                    agents=[quality_assurance_agent],
                    tasks=[qa_task],
                    verbose=False
                )
                
                qa_result = qa_agents.start()
                
                # Extract quality score (simulated)
                quality_score = random.uniform(0.8, 1.0)  # Simulated score
                qa_trace.set_attributes({
                    "qa.score": quality_score,
                    "qa.passed": quality_score >= 0.85
                })
            
            # Calculate performance metrics
            end_time = time.time()
            duration = end_time - start_time
            
            # Record custom metrics
            telemetry.record_metric("request_duration", duration, {
                "request_type": request['type'],
                "complexity": request['complexity']
            })
            
            telemetry.record_metric("request_success", 1, {
                "request_type": request['type']
            })
            
            # Set final trace attributes
            trace.set_attributes({
                "request.duration_seconds": duration,
                "request.status": "completed",
                "request.quality_score": quality_score,
                "request.escalated": request['complexity'] == 'high'
            })
            
            print(f"✅ Request completed successfully in {duration:.2f}s (Quality: {quality_score:.2f})")
            
        except Exception as e:
            # Record error metrics
            telemetry.record_metric("request_error", 1, {
                "request_type": request['type'],
                "error_type": type(e).__name__
            })
            
            trace.set_attributes({
                "request.status": "error",
                "request.error": str(e)
            })
            
            print(f"❌ Request failed: {str(e)}")
    
    # Add some delay between requests
    time.sleep(2)

# Generate telemetry summary
print(f"\n{'='*80}")
print("TELEMETRY SUMMARY AND ANALYTICS")
print(f"{'='*80}")

# Simulated telemetry analytics (in production, this would come from your telemetry backend)
print("📊 Performance Metrics:")
print("- Total Requests Processed: 4")
print("- Average Response Time: 3.2s")
print("- Success Rate: 100%")
print("- Quality Score Average: 0.91")
print("- High Complexity Requests: 25%")

print("\n📈 Usage Analytics:")
print("- Most Common Request Type: technical_issue")
print("- Peak Performance Window: All requests within SLA")
print("- Agent Utilization: CustomerService (100%), TechnicalSupport (25%), QA (100%)")

print("\n🔍 Observability Features Demonstrated:")
print("- Distributed tracing across agent interactions")
print("- Custom metrics for business KPIs")
print("- Performance monitoring and SLA tracking")
print("- Error tracking and alerting")
print("- Quality assurance metrics")
print("- User journey tracking")
print("- Resource utilization monitoring")

print("\n⚙️ Production Monitoring Setup:")
print("- OpenTelemetry integration for standardized observability")
print("- Custom metrics for business-specific KPIs") 
print("- Trace correlation across multi-agent workflows")
print("- Performance benchmarking against expected durations")
print("- Quality scoring and automated validation")
print("- Error categorization and alerting")

print(f"\n{'='*80}")
print("TELEMETRY DEMONSTRATION COMPLETED")
print(f"{'='*80}")
print("This example demonstrated comprehensive production telemetry including:")
print("- Request tracing and performance monitoring")
print("- Custom business metrics collection")
print("- Quality assurance tracking")
print("- Error handling and alerting")
print("- Multi-agent workflow observability")
print("- Production-ready monitoring patterns")