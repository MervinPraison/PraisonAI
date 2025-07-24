#!/usr/bin/env python3
"""
Context Engineering Workflow - Advanced Multi-Agent Example

This example demonstrates advanced Context Engineering workflows using ContextAgent
in combination with other PraisonAI agents. It shows how Context Engineering can
dramatically improve AI implementation success rates through comprehensive context
generation and validation loops.

Workflow demonstrated:
1. Product Manager Agent defines requirements
2. ContextAgent analyzes codebase and generates comprehensive context
3. Architecture Agent designs implementation using context
4. Developer Agent implements using context-enhanced prompts
5. QA Agent validates using context-generated criteria

This represents the full Context Engineering methodology in action.
"""

import sys
from pathlib import Path

# Add the src directory to Python path for imports
project_root = Path(__file__).parent.parent.parent.parent / "src" / "praisonai-agents"
sys.path.insert(0, str(project_root))

from praisonaiagents import Agent, Task, PraisonAIAgents, create_context_agent

class ContextEngineeringWorkflow:
    """
    Advanced Context Engineering workflow demonstrating the full methodology.
    
    This class orchestrates multiple agents using Context Engineering principles
    to achieve higher success rates in AI-driven development tasks.
    """
    
    def __init__(self, project_path: str, llm: str = "gpt-4o-mini"):
        self.project_path = project_path
        self.llm = llm
        self.context_data = {}
        self.setup_agents()
    
    def setup_agents(self):
        """Setup the multi-agent team with Context Engineering support."""
        
        # 1. Product Manager Agent - Defines requirements
        self.product_manager = Agent(
            name="Product Manager",
            role="Product Requirements Specialist",
            goal="Define clear, comprehensive product requirements and user stories",
            backstory="""You are an experienced product manager who specializes in 
            creating detailed, actionable requirements. You understand that clear 
            requirements are the foundation of successful implementation.""",
            instructions="""
            When defining requirements:
            1. Be specific and measurable
            2. Include user acceptance criteria
            3. Consider edge cases and error scenarios
            4. Define success metrics
            5. Specify technical constraints
            """,
            llm=self.llm,
            verbose=True
        )
        
        # 2. Context Engineering Agent - Generates comprehensive context
        self.context_engineer = create_context_agent(
            llm=self.llm,
            name="Context Engineering Specialist",
            verbose=True
        )
        
        # 3. Software Architect Agent - Designs implementation using context
        self.architect = Agent(
            name="Software Architect",
            role="System Architecture Specialist", 
            goal="Design robust, scalable system architecture based on comprehensive context",
            backstory="""You are a senior software architect with expertise in 
            designing systems that follow established patterns and best practices. 
            You excel at creating architectures that integrate seamlessly with 
            existing codebases.""",
            instructions="""
            When designing architecture:
            1. Follow the patterns identified in the context analysis
            2. Ensure compatibility with existing systems
            3. Design for scalability and maintainability
            4. Consider security and performance implications
            5. Document architectural decisions and rationale
            """,
            llm=self.llm,
            verbose=True
        )
        
        # 4. Senior Developer Agent - Implements using context-enhanced guidance
        self.developer = Agent(
            name="Senior Developer",
            role="Implementation Specialist",
            goal="Implement features following context-guided best practices",
            backstory="""You are a senior developer who excels at implementing 
            features that follow established codebase patterns. You understand 
            that consistency and quality are paramount.""",
            instructions="""
            When implementing features:
            1. Follow the codebase patterns identified in context analysis
            2. Maintain consistency with existing code style
            3. Implement comprehensive error handling
            4. Write clean, maintainable code
            5. Follow the implementation blueprint exactly
            """,
            llm=self.llm,
            verbose=True
        )
        
        # 5. QA Engineer Agent - Validates using context-generated criteria
        self.qa_engineer = Agent(
            name="QA Engineer",
            role="Quality Assurance Specialist",
            goal="Ensure implementation meets all quality criteria and requirements",
            backstory="""You are an experienced QA engineer who specializes in 
            comprehensive testing and validation. You understand that quality 
            is built in, not bolted on.""",
            instructions="""
            When validating implementations:
            1. Use the validation criteria from context analysis
            2. Test both happy path and edge cases
            3. Verify integration with existing systems
            4. Check for security vulnerabilities
            5. Validate performance requirements
            """,
            llm=self.llm,
            verbose=True
        )
    
    def run_context_engineering_workflow(self, feature_request: str):
        """
        Execute the complete Context Engineering workflow.
        
        Args:
            feature_request (str): The feature to be implemented
            
        Returns:
            dict: Complete workflow results with context and implementation
        """
        print(f"🚀 Starting Context Engineering Workflow")
        print(f"Feature Request: {feature_request}")
        print("=" * 80)
        
        # Phase 1: Requirements Analysis
        print("\n📋 Phase 1: Product Requirements Analysis")
        print("-" * 50)
        
        requirements_task = Task(
            name="requirements_analysis",
            description=f"""
            Analyze and refine the feature request: '{feature_request}'
            
            Create comprehensive requirements including:
            - Detailed feature description
            - User acceptance criteria
            - Technical requirements
            - Success metrics
            - Edge cases and constraints
            """,
            expected_output="Comprehensive product requirements document",
            agent=self.product_manager
        )
        
        # Phase 2: Context Engineering Analysis
        print("\n🔧 Phase 2: Context Engineering Analysis")
        print("-" * 50)
        
        # Generate comprehensive context using ContextAgent
        codebase_analysis = self.context_engineer.analyze_codebase_patterns(
            project_path=self.project_path
        )
        
        context_document = self.context_engineer.generate_context_document(
            project_path=self.project_path,
            requirements=feature_request,
            analysis=codebase_analysis
        )
        
        validation_framework = self.context_engineer.create_validation_loop(
            implementation_requirements=feature_request,
            success_criteria=[
                "Feature implements all specified requirements",
                "Code follows existing patterns and conventions",
                "Implementation includes comprehensive error handling",
                "All tests pass and coverage meets standards",
                "Integration with existing systems is seamless"
            ]
        )
        
        implementation_blueprint = self.context_engineer.create_implementation_blueprint(
            feature_request=feature_request,
            context_analysis=codebase_analysis
        )
        
        # Generate PRP for complete context
        prp = self.context_engineer.generate_prp(
            feature_request=feature_request,
            context_analysis=codebase_analysis,
            documentation_links=[
                "https://docs.praisonai.com/",
                "https://pydantic-docs.helpmanual.io/",
                "https://fastapi.tiangolo.com/"
            ]
        )
        
        print(f"✅ Context Engineering Analysis Complete:")
        print(f"   • Codebase analysis: {len(str(codebase_analysis))} chars")
        print(f"   • Context document: {len(context_document)} chars")
        print(f"   • Validation framework: {len(validation_framework['validation_steps'])} steps")
        print(f"   • Implementation blueprint: {len(implementation_blueprint['implementation_steps'])} steps")
        print(f"   • PRP generated: {len(prp)} chars")
        
        # Store context data for subsequent phases
        self.context_data = {
            "codebase_analysis": codebase_analysis,
            "context_document": context_document,
            "validation_framework": validation_framework,
            "implementation_blueprint": implementation_blueprint,
            "prp": prp
        }
        
        # Phase 3: Architecture Design with Context
        print("\n🏗️ Phase 3: Architecture Design with Context")
        print("-" * 50)
        
        architecture_task = Task(
            name="architecture_design",
            description=f"""
            Design system architecture for: '{feature_request}'
            
            Use the comprehensive context provided:
            {context_document}
            
            Implementation Blueprint:
            {implementation_blueprint}
            
            Design architecture that:
            - Follows identified codebase patterns
            - Integrates with existing systems
            - Meets all technical requirements
            - Is scalable and maintainable
            """,
            expected_output="Detailed system architecture design with component specifications",
            agent=self.architect,
            context=[requirements_task]
        )
        
        # Phase 4: Implementation with Context-Enhanced Guidance
        print("\n💻 Phase 4: Implementation with Context")
        print("-" * 50)
        
        # Enhance the implementation prompt with context
        enhanced_prompt = self.context_engineer.enhance_prompt_with_context(
            base_prompt=f"Implement {feature_request}",
            context_data=codebase_analysis
        )
        
        implementation_task = Task(
            name="feature_implementation",
            description=f"""
            Implement the feature using context-enhanced guidance:
            
            {enhanced_prompt}
            
            Product Requirements Prompt (PRP):
            {prp}
            
            Architecture Design: Reference the architecture task output
            
            Implementation must:
            - Follow the implementation blueprint exactly
            - Use patterns identified in codebase analysis
            - Meet all requirements from Phase 1
            - Include comprehensive error handling
            """,
            expected_output="Complete feature implementation with code and documentation",
            agent=self.developer,
            context=[requirements_task, architecture_task]
        )
        
        # Phase 5: Quality Assurance with Context-Generated Criteria
        print("\n🔍 Phase 5: Quality Assurance with Context")
        print("-" * 50)
        
        qa_task = Task(
            name="quality_validation",
            description=f"""
            Validate the implementation using context-generated criteria:
            
            Validation Framework:
            {validation_framework}
            
            Verify that implementation:
            - Meets all success criteria defined in validation framework
            - Follows codebase patterns and conventions
            - Integrates properly with existing systems
            - Handles edge cases and error scenarios
            - Meets performance and security requirements
            
            Use the validation steps provided to systematically check each criterion.
            """,
            expected_output="Comprehensive quality validation report with pass/fail status",
            agent=self.qa_engineer,
            context=[requirements_task, architecture_task, implementation_task]
        )
        
        # Execute the complete workflow
        print("\n⚙️ Executing Context Engineering Workflow")
        print("-" * 50)
        
        agents_workflow = PraisonAIAgents(
            agents=[
                self.product_manager,
                self.architect, 
                self.developer,
                self.qa_engineer
            ],
            tasks=[
                requirements_task,
                architecture_task,
                implementation_task,
                qa_task
            ],
            process="sequential",
            verbose=True
        )
        
        # Execute workflow
        workflow_results = agents_workflow.start()
        
        # Compile complete results
        complete_results = {
            "feature_request": feature_request,
            "context_engineering": self.context_data,
            "workflow_results": workflow_results,
            "methodology": "Context Engineering - 10x better than prompt engineering"
        }
        
        return complete_results

def demonstrate_context_engineering_benefits():
    """
    Demonstrate the benefits of Context Engineering methodology.
    """
    print("\n📊 Context Engineering vs Traditional Approaches")
    print("=" * 60)
    
    # Traditional approach simulation
    print("\n❌ Traditional AI Coding Approach:")
    print("   1. Write basic prompt: 'Implement user authentication'")
    print("   2. AI uses general knowledge to implement")
    print("   3. Result often doesn't fit existing codebase patterns")
    print("   4. Multiple iterations needed to fix integration issues")
    print("   5. Success rate: ~30-40% first-try success")
    
    # Context Engineering approach
    print("\n✅ Context Engineering Approach:")
    print("   1. Analyze codebase patterns and architecture")
    print("   2. Generate comprehensive context document")
    print("   3. Create validation framework with success criteria")
    print("   4. Enhance prompts with rich contextual information")
    print("   5. Generate PRP (Product Requirements Prompt)")
    print("   6. AI implements using complete context")
    print("   7. Success rate: ~90%+ first-try success")
    
    print("\n📈 Context Engineering Advantages:")
    print("   • 10x better than prompt engineering (context vs clever wording)")
    print("   • 100x better than vibe coding (structured vs ad-hoc)")
    print("   • Enables first-try implementation success")
    print("   • Reduces development iteration cycles")
    print("   • Ensures consistency with existing codebase")
    print("   • Provides built-in quality validation")

def run_example_workflow():
    """Run an example Context Engineering workflow."""
    
    # Setup workflow with current project
    project_path = str(project_root)
    workflow = ContextEngineeringWorkflow(
        project_path=project_path,
        llm="gpt-4o-mini"
    )
    
    # Example feature request
    feature_request = """
    Implement a real-time notification system that:
    - Sends notifications via WebSocket connections
    - Supports different notification types (info, warning, error)
    - Persists notifications in database for offline users
    - Includes user preference management for notification settings
    - Provides REST API for notification management
    """
    
    print("🎯 Running Example Context Engineering Workflow")
    print("=" * 60)
    
    try:
        # Execute the complete workflow
        results = workflow.run_context_engineering_workflow(feature_request)
        
        print("\n🎉 Context Engineering Workflow Completed Successfully!")
        print("=" * 60)
        
        print(f"\n📊 Workflow Summary:")
        print(f"   • Feature: Real-time notification system")
        print(f"   • Context generated: ✅ Complete")
        print(f"   • Architecture designed: ✅ With context")
        print(f"   • Implementation: ✅ Context-guided")
        print(f"   • Quality validation: ✅ Context-criteria")
        
        print(f"\n🔧 Context Engineering Data:")
        context_data = results["context_engineering"]
        print(f"   • Codebase analysis: {len(str(context_data['codebase_analysis']))} chars")
        print(f"   • Context document: {len(context_data['context_document'])} chars") 
        print(f"   • Validation framework: {len(context_data['validation_framework']['validation_steps'])} steps")
        print(f"   • Implementation blueprint: {len(context_data['implementation_blueprint']['implementation_steps'])} steps")
        print(f"   • PRP: {len(context_data['prp'])} chars")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error in workflow execution: {e}")
        print("   Note: This is a demonstration - actual execution requires proper environment setup")
        return None

if __name__ == "__main__":
    print("🚀 Advanced Context Engineering Workflow Example")
    print("================================================")
    
    print("\n💡 This example demonstrates the complete Context Engineering methodology:")
    print("   • Comprehensive codebase analysis")
    print("   • Context document generation")
    print("   • Validation framework creation")
    print("   • Multi-agent workflow with context integration")
    print("   • Quality assurance with context-generated criteria")
    
    # Show benefits comparison
    demonstrate_context_engineering_benefits()
    
    # Run example workflow (demo mode)
    print("\n🎭 Demo Mode: Context Engineering Workflow Structure")
    print("(Note: Full execution requires complete environment setup)")
    
    project_path = str(project_root)
    workflow = ContextEngineeringWorkflow(project_path, "gpt-4o-mini")
    
    print(f"\n✅ Workflow Setup Complete:")
    print(f"   • Project path: {project_path}")
    print(f"   • Agents configured: 5 (PM, Context Engineer, Architect, Developer, QA)")
    print(f"   • Context Engineering agent: ✅ Ready")
    print(f"   • Multi-agent workflow: ✅ Configured")
    
    print(f"\n🎯 Ready to execute Context Engineering workflow!")
    print(f"   Use workflow.run_context_engineering_workflow(feature_request)")
    print(f"   to execute the complete methodology.")
    
    print(f"\n📚 Key Context Engineering Concepts Demonstrated:")
    print(f"   • Pattern extraction from existing codebase")
    print(f"   • Comprehensive context document generation")
    print(f"   • Validation loop creation with success criteria")
    print(f"   • PRP (Product Requirements Prompt) generation")
    print(f"   • Context-enhanced prompt engineering")
    print(f"   • Multi-agent workflow integration")
    
    print(f"\n🎉 Context Engineering: 10x better than prompt engineering, 100x better than vibe coding!")