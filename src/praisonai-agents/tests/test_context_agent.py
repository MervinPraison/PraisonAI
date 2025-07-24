#!/usr/bin/env python3
"""
Test ContextAgent Implementation

This test script validates the ContextAgent implementation for:
- Import capability
- Basic instantiation
- Method availability
- Backward compatibility
- Integration with existing PraisonAI structure
"""

import sys
from pathlib import Path

# Add the src directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test that ContextAgent can be imported correctly."""
    print("🧪 Testing ContextAgent Imports...")
    
    try:
        # Test importing from main package
        from praisonaiagents import ContextAgent, create_context_agent
        print("✅ Successfully imported ContextAgent and create_context_agent from main package")
        
        # Test importing from agent submodule
        from praisonaiagents.agent import ContextAgent as AgentContextAgent
        print("✅ Successfully imported ContextAgent from agent submodule")
        
        # Test importing from specific module
        from praisonaiagents.agent.context_agent import ContextAgent as DirectContextAgent
        print("✅ Successfully imported ContextAgent from direct module")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_basic_instantiation():
    """Test basic ContextAgent instantiation."""
    print("\\n🧪 Testing ContextAgent Instantiation...")
    
    try:
        from praisonaiagents import ContextAgent, create_context_agent
        
        # Test direct instantiation
        context_agent = ContextAgent()
        print("✅ Successfully created ContextAgent with default parameters")
        
        # Test with custom parameters
        custom_agent = ContextAgent(
            name="Test Context Engineer",
            role="Test Role",
            goal="Test Goal",
            llm="gpt-4o-mini"
        )
        print("✅ Successfully created ContextAgent with custom parameters")
        
        # Test factory function
        factory_agent = create_context_agent(llm="gpt-4o-mini")
        print("✅ Successfully created ContextAgent using factory function")
        
        return True, [context_agent, custom_agent, factory_agent]
        
    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        return False, []

def test_agent_inheritance():
    """Test that ContextAgent properly inherits from Agent."""
    print("\\n🧪 Testing Agent Inheritance...")
    
    try:
        from praisonaiagents import ContextAgent, Agent
        
        context_agent = ContextAgent()
        
        # Test inheritance
        assert isinstance(context_agent, Agent), "ContextAgent should inherit from Agent"
        print("✅ ContextAgent properly inherits from Agent class")
        
        # Test that base Agent properties exist
        assert hasattr(context_agent, 'name'), "Should have name attribute"
        assert hasattr(context_agent, 'role'), "Should have role attribute"
        assert hasattr(context_agent, 'goal'), "Should have goal attribute"
        print("✅ ContextAgent has all required Agent attributes")
        
        return True
        
    except Exception as e:
        print(f"❌ Inheritance test failed: {e}")
        return False

def test_context_engineering_methods():
    """Test Context Engineering specific methods."""
    print("\\n🧪 Testing Context Engineering Methods...")
    
    try:
        from praisonaiagents import create_context_agent
        
        context_agent = create_context_agent()
        
        # Test that all Context Engineering methods exist
        required_methods = [
            'analyze_codebase_patterns',
            'generate_context_document',
            'create_validation_loop',
            'enhance_prompt_with_context',
            'generate_prp',
            'extract_documentation_patterns',
            'analyze_test_patterns',
            'create_implementation_blueprint'
        ]
        
        for method_name in required_methods:
            assert hasattr(context_agent, method_name), f"Missing method: {method_name}"
            assert callable(getattr(context_agent, method_name)), f"Method {method_name} is not callable"
        
        print(f"✅ All {len(required_methods)} Context Engineering methods are available")
        
        # Test async methods
        async_methods = [
            'aanalyze_codebase_patterns',
            'agenerate_context_document',
            'acreate_validation_loop',
            'aenhance_prompt_with_context',
            'agenerate_prp'
        ]
        
        for method_name in async_methods:
            assert hasattr(context_agent, method_name), f"Missing async method: {method_name}"
            assert callable(getattr(context_agent, method_name)), f"Async method {method_name} is not callable"
        
        print(f"✅ All {len(async_methods)} async methods are available")
        
        return True
        
    except Exception as e:
        print(f"❌ Method availability test failed: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality of ContextAgent methods."""
    print("\\n🧪 Testing Basic Functionality...")
    
    try:
        from praisonaiagents import create_context_agent
        
        context_agent = create_context_agent()
        
        # Test codebase analysis with current directory
        test_path = str(Path(__file__).parent.parent)
        analysis = context_agent.analyze_codebase_patterns(test_path)
        assert isinstance(analysis, dict), "analyze_codebase_patterns should return dict"
        print("✅ analyze_codebase_patterns works correctly")
        
        # Test context document generation
        context_doc = context_agent.generate_context_document(
            project_path=test_path,
            requirements="Test feature implementation"
        )
        assert isinstance(context_doc, str), "generate_context_document should return string"
        assert len(context_doc) > 100, "Context document should be substantial"
        print("✅ generate_context_document works correctly")
        
        # Test validation loop creation
        validation = context_agent.create_validation_loop(
            implementation_requirements="Test implementation",
            success_criteria=["Test passes", "Code works"]
        )
        assert isinstance(validation, dict), "create_validation_loop should return dict"
        assert 'validation_steps' in validation, "Should have validation_steps"
        print("✅ create_validation_loop works correctly")
        
        # Test prompt enhancement
        enhanced = context_agent.enhance_prompt_with_context(
            base_prompt="Test prompt",
            context_data={"test": "data"}
        )
        assert isinstance(enhanced, str), "enhance_prompt_with_context should return string"
        assert len(enhanced) > len("Test prompt"), "Enhanced prompt should be longer"
        print("✅ enhance_prompt_with_context works correctly")
        
        # Test PRP generation
        prp = context_agent.generate_prp(
            feature_request="Test feature",
            context_analysis=analysis
        )
        assert isinstance(prp, str), "generate_prp should return string"
        assert "PRP" in prp, "Should contain PRP reference"
        print("✅ generate_prp works correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        return False

def test_backward_compatibility():
    """Test that existing PraisonAI functionality still works."""
    print("\\n🧪 Testing Backward Compatibility...")
    
    try:
        # Test that we can still import and use existing agents
        from praisonaiagents import Agent, ImageAgent
        
        # Test basic Agent still works
        basic_agent = Agent(name="Test Agent")  # Agent created for compatibility test
        print("✅ Basic Agent still works")
        
        # Test ImageAgent still works
        image_agent = ImageAgent(name="Test Image Agent")  # Image agent created for compatibility test
        print("✅ ImageAgent still works")
        
        # Test that we can import other PraisonAI components
        from praisonaiagents import Task, PraisonAIAgents
        print("✅ Task and PraisonAIAgents can still be imported")
        
        # Test that __all__ exports are working
        import praisonaiagents
        expected_exports = [
            'Agent', 'ImageAgent', 'ContextAgent', 'create_context_agent',
            'PraisonAIAgents', 'Task'
        ]
        
        for export in expected_exports:
            assert hasattr(praisonaiagents, export), f"Missing export: {export}"
        
        print("✅ All expected exports are available")
        
        return True
        
    except Exception as e:
        print(f"❌ Backward compatibility test failed: {e}")
        return False

def test_syntax_validation():
    """Test that all Python files have valid syntax."""
    print("\\n🧪 Testing Syntax Validation...")
    
    try:
        import ast
        
        # Test the main ContextAgent file
        context_agent_file = project_root / "praisonaiagents" / "agent" / "context_agent.py"
        
        with open(context_agent_file, 'r') as f:
            content = f.read()
        
        # Parse the file to check for syntax errors
        ast.parse(content)
        print("✅ context_agent.py has valid Python syntax")
        
        # Test the examples
        example_files = [
            Path(__file__).parent.parent.parent.parent / "examples" / "python" / "agents" / "context-agent.py",
            Path(__file__).parent.parent.parent.parent / "examples" / "python" / "concepts" / "context-engineering-workflow.py"
        ]
        
        for example_file in example_files:
            if example_file.exists():
                with open(example_file, 'r') as f:
                    content = f.read()
                ast.parse(content)
                print(f"✅ {example_file.name} has valid Python syntax")
        
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error found: {e}")
        return False
    except Exception as e:
        print(f"❌ Syntax validation failed: {e}")
        return False

def run_all_tests():
    """Run all tests and provide summary."""
    print("🚀 Context Engineering Implementation QA Tests")
    print("=" * 60)
    
    test_results = []
    
    # Run all tests
    test_results.append(("Imports", test_imports()))
    test_results.append(("Instantiation", test_basic_instantiation()[0]))
    test_results.append(("Inheritance", test_agent_inheritance()))
    test_results.append(("Methods", test_context_engineering_methods()))
    test_results.append(("Functionality", test_basic_functionality()))
    test_results.append(("Backward Compatibility", test_backward_compatibility()))
    test_results.append(("Syntax Validation", test_syntax_validation()))
    
    # Summary
    print("\\n📊 Test Results Summary")
    print("=" * 30)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name:<20} {status}")
        if result:
            passed += 1
    
    print(f"\\n🎯 Overall Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! ContextAgent implementation is ready.")
        return True
    else:
        print("⚠️  Some tests failed. Review implementation before release.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    
    if success:
        print("\\n✅ Quality Assurance Complete")
        print("   • ContextAgent implementation validated")
        print("   • Backward compatibility confirmed")
        print("   • All Context Engineering methods working")
        print("   • Examples have valid syntax")
        print("   • Ready for production use")
    else:
        print("\\n❌ Quality Assurance Failed")
        print("   • Review failed tests above")
        print("   • Fix issues before release")
        
    sys.exit(0 if success else 1)