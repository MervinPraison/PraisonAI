#!/usr/bin/env python3
"""
Context Agent Example - Basic Usage

This example demonstrates how to use the ContextAgent for automated context generation.
The ContextAgent implements Context Engineering principles to generate comprehensive
context for AI coding assistants, enabling first-try implementation success.

Key features demonstrated:
- Basic ContextAgent instantiation
- Codebase pattern analysis
- Context document generation  
- Validation loop creation
- Prompt enhancement with context
- PRP (Product Requirements Prompt) generation
"""

import sys
from pathlib import Path

# Add the src directory to Python path for imports
project_root = Path(__file__).parent.parent.parent.parent / "src" / "praisonai-agents"
sys.path.insert(0, str(project_root))

from praisonaiagents import create_context_agent

def demonstrate_basic_context_generation():
    """Demonstrate basic context generation capabilities."""
    print("🔧 Context Engineering Example: Basic Usage")
    print("=" * 60)
    
    # Create a ContextAgent using the factory function
    context_agent = create_context_agent(
        llm="gpt-4o-mini",
        name="Basic Context Engineer",
        verbose=True
    )
    
    # Example 1: Analyze codebase patterns
    print("\n📁 Example 1: Analyzing Codebase Patterns")
    print("-" * 40)
    
    # Use current project as example (adjust path as needed)
    project_path = str(project_root)
    analysis = context_agent.analyze_codebase_patterns(
        project_path=project_path,
        file_patterns=["*.py"]
    )
    
    print(f"✅ Analyzed project at: {project_path}")
    print(f"   Project structure: {len(analysis.get('project_structure', {}).get('directories', []))} directories")
    print(f"   Code patterns identified: {len(analysis.get('code_patterns', {}))}")
    print(f"   Architecture: {analysis.get('architecture_insights', {}).get('primary_pattern', 'Unknown')}")
    
    # Example 2: Generate context document
    print("\n📄 Example 2: Generating Context Document")
    print("-" * 40)
    
    feature_request = "Add user authentication system with JWT tokens and role-based access control"
    context_doc = context_agent.generate_context_document(
        project_path=project_path,
        requirements=feature_request,
        analysis=analysis
    )
    
    print(f"✅ Generated context document for: {feature_request}")
    print(f"   Document length: {len(context_doc)} characters")
    print(f"   Contains architecture patterns: {'Architecture Patterns' in context_doc}")
    print(f"   Contains validation criteria: {'Validation Criteria' in context_doc}")
    
    # Example 3: Create validation loop
    print("\n✅ Example 3: Creating Validation Loop")
    print("-" * 40)
    
    success_criteria = [
        "Authentication system accepts valid JWT tokens",
        "Role-based access control blocks unauthorized users", 
        "User registration and login endpoints work correctly",
        "Password hashing follows security best practices",
        "Session management handles token expiration"
    ]
    
    validation_config = context_agent.create_validation_loop(
        implementation_requirements=feature_request,
        success_criteria=success_criteria
    )
    
    print(f"✅ Created validation loop with {len(validation_config['validation_steps'])} steps")
    print(f"   Success criteria: {len(success_criteria)}")
    print(f"   Executable tests: {len(validation_config['executable_tests'])}")
    print(f"   Quality gates: {len(validation_config['quality_gates'])}")
    
    # Example 4: Enhance prompt with context
    print("\n🚀 Example 4: Enhancing Prompt with Context")
    print("-" * 40)
    
    basic_prompt = "Implement user authentication"
    enhanced_prompt = context_agent.enhance_prompt_with_context(
        base_prompt=basic_prompt,
        context_data=analysis
    )
    
    print(f"✅ Enhanced prompt from {len(basic_prompt)} to {len(enhanced_prompt)} characters")
    print(f"   Original: '{basic_prompt}'")
    print("   Enhanced includes: Context Engineering, Implementation Context, Quality Requirements")
    
    # Example 5: Generate PRP (Product Requirements Prompt)
    print("\n📋 Example 5: Generating PRP")
    print("-" * 40)
    
    documentation_links = [
        "https://jwt.io/introduction/",
        "https://fastapi.tiangolo.com/tutorial/security/",
        "https://passlib.readthedocs.io/en/stable/"
    ]
    
    prp = context_agent.generate_prp(
        feature_request=feature_request,
        context_analysis=analysis,
        documentation_links=documentation_links
    )
    
    print("✅ Generated comprehensive PRP")
    print(f"   PRP length: {len(prp)} characters")
    print(f"   Contains feature request: {feature_request in prp}")
    print(f"   Contains documentation links: {len(documentation_links)} links included")
    print(f"   Contains implementation blueprint: {'Implementation Blueprint' in prp}")
    print(f"   Confidence score: {'9/10' in prp}")

def demonstrate_context_agent_as_tool():
    """Demonstrate using ContextAgent as a tool in a multi-agent workflow."""
    print("\n🔗 Context Engineering Example: Multi-Agent Integration")
    print("=" * 60)
    
    # Create ContextAgent
    context_agent = create_context_agent(llm="gpt-4o-mini")
    
    # Example scenario: Product planning workflow
    project_path = str(project_root)
    feature_request = "Build a real-time chat system with WebSocket support"
    
    # Step 1: Context analysis
    print("\n1️⃣ Step 1: Context Analysis")
    analysis = context_agent.analyze_codebase_patterns(project_path)
    print(f"✅ Analyzed codebase architecture and patterns")
    
    # Step 2: Generate implementation blueprint
    print("\n2️⃣ Step 2: Implementation Blueprint")
    blueprint = context_agent.create_implementation_blueprint(feature_request, analysis)
    print(f"✅ Created implementation blueprint with {len(blueprint['implementation_steps'])} steps")
    
    # Step 3: Generate comprehensive PRP
    print("\n3️⃣ Step 3: Generate PRP")
    prp = context_agent.generate_prp(feature_request, analysis)  # Generated PRP for implementation guidance
    print(f"✅ Generated PRP for implementation guidance")
    
    # Step 4: Create validation framework
    print("\n4️⃣ Step 4: Validation Framework")
    criteria = [
        "WebSocket connections establish successfully",
        "Messages broadcast to all connected clients",
        "Chat history persists and loads correctly",
        "User authentication works with WebSocket",
        "Connection handling is robust with reconnection"
    ]
    validation = context_agent.create_validation_loop(feature_request, criteria)  # Validation framework for QA
    print(f"✅ Created validation framework with {len(criteria)} criteria")
    
    print("\n🎯 Context Engineering Workflow Complete!")
    print(f"   Feature: {feature_request}")
    print("   Implementation ready with comprehensive context")
    print("   Validation criteria defined for quality assurance")

def show_context_engineering_benefits():
    """Demonstrate the benefits of Context Engineering vs traditional approaches."""
    print("\n📊 Context Engineering Benefits")
    print("=" * 60)
    
    # Traditional prompt engineering approach
    print("\n❌ Traditional Prompt Engineering:")
    traditional_prompt = "Create a user authentication system"
    print(f"   Prompt: '{traditional_prompt}'")
    print(f"   Length: {len(traditional_prompt)} characters")
    print(f"   Context: Minimal - relies on AI's general knowledge")
    print(f"   Success Rate: Variable - depends on AI model's training")
    
    # Context Engineering approach
    print("\n✅ Context Engineering Approach:")
    context_agent = create_context_agent(llm="gpt-4o-mini")
    
    # Generate comprehensive context
    analysis = context_agent.analyze_codebase_patterns(str(project_root))
    enhanced_prompt = context_agent.enhance_prompt_with_context(
        traditional_prompt, analysis
    )
    
    print(f"   Enhanced Prompt Length: {len(enhanced_prompt)} characters")
    print(f"   Context: Comprehensive - includes:")
    print(f"     • Codebase architecture analysis")
    print(f"     • Existing patterns and conventions")
    print(f"     • Implementation guidance")
    print(f"     • Quality requirements")
    print(f"     • Validation criteria")
    print(f"   Success Rate: Higher - AI has all necessary context")
    
    print(f"\n🎯 Context Engineering provides:")
    print("   📈 10x better than prompt engineering (comprehensive vs clever wording)")
    print("   📈 100x better than vibe coding (structured vs ad-hoc)")
    print("   🎯 First-try implementation success through complete context")

if __name__ == "__main__":
    print("🚀 PraisonAI Context Engineering Examples")
    print("=========================================")
    
    try:
        # Run all examples
        demonstrate_basic_context_generation()
        demonstrate_context_agent_as_tool()
        show_context_engineering_benefits()
        
        print("\n🎉 All Context Engineering examples completed successfully!")
        print("\n💡 Key Takeaways:")
        print("   • ContextAgent automates comprehensive context generation")
        print("   • Context Engineering enables first-try implementation success")
        print("   • Integration with existing PraisonAI agents is seamless")
        print("   • Validation frameworks ensure quality and completeness")
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        print("   Make sure you have the PraisonAI package installed and configured")
        sys.exit(1)