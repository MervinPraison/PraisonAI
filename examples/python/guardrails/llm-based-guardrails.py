#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agents with LLM-based guardrails (using natural language descriptions)
marketing_agent = Agent(
    name="Marketing Writer",
    role="Marketing Content Creator",
    goal="Create engaging marketing content",
    backstory="You are a skilled marketing writer who creates compelling promotional content.",
    llm="gpt-4o-mini"
)

technical_agent = Agent(
    name="Technical Writer",
    role="Technical Documentation Writer",
    goal="Write clear technical documentation",
    backstory="You are a technical writer who creates clear, accurate technical documentation.",
    llm="gpt-4o-mini"
)

customer_service_agent = Agent(
    name="Customer Service Representative",
    role="Customer Support Specialist",
    goal="Provide helpful customer service responses",
    backstory="You are a customer service representative who provides helpful, professional support.",
    llm="gpt-4o-mini"
)

# Create tasks with LLM-based guardrails (natural language descriptions)
marketing_task = Task(
    name="create_marketing_content",
    description="Create a marketing email for a new product launch",
    expected_output="Engaging marketing email that drives action",
    agent=marketing_agent,
    guardrail="Ensure the content is professional, engaging, free of errors, includes a clear call-to-action, and maintains an appropriate tone for business communication. The content should be persuasive but not pushy.",
    max_retries=2
)

technical_task = Task(
    name="write_technical_doc",
    description="Write documentation for a REST API endpoint",
    expected_output="Clear technical documentation with examples",
    agent=technical_agent,
    guardrail="Ensure the documentation is accurate, well-structured, includes code examples, uses proper technical terminology, and is easy to understand for developers. Check for completeness and clarity.",
    max_retries=2
)

customer_service_task = Task(
    name="handle_customer_inquiry",
    description="Respond to a customer complaint about delayed shipping",
    expected_output="Professional customer service response",
    agent=customer_service_agent,
    guardrail="Ensure the response is empathetic, professional, offers a solution, apologizes appropriately, and maintains a helpful tone. The response should address the customer's concern directly and provide next steps.",
    max_retries=2
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[marketing_agent, technical_agent, customer_service_agent],
    tasks=[marketing_task, technical_task, customer_service_task],
    process="sequential",
    verbose=True
)

# Run the workflow
if __name__ == "__main__":
    print("🤖 LLM-based Guardrails Example")
    print("This example shows how to use natural language descriptions as guardrails")
    print("=" * 80)
    
    print("\n📝 Natural Language Guardrails:")
    print("• Marketing: Professional, engaging, with clear call-to-action")
    print("• Technical: Accurate, well-structured, with code examples")  
    print("• Customer Service: Empathetic, professional, solution-focused")
    
    print("\n⚙️ How it works:")
    print("1. Guardrails are written in natural language describing quality criteria")
    print("2. An LLM evaluates the output against these criteria")
    print("3. If evaluation fails, the agent retries with feedback")
    print("4. No custom code needed - just describe what you want")
    
    result = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ LLM-based Guardrails Complete")
    print("💡 All outputs were validated using natural language descriptions")
    print("🔧 LLM guardrails provide flexible, context-aware validation")
    print("🎯 Perfect for complex quality criteria that are hard to code")