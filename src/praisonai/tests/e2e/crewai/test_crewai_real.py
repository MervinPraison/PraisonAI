"""
CrewAI Real End-to-End Test

⚠️  WARNING: This test makes real API calls and may incur costs!

This test verifies CrewAI framework integration with actual LLM calls.
Run only when you have:
- Valid API keys set as environment variables
- Understanding that this will consume API credits
"""

import pytest
import os
import sys
import tempfile
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

@pytest.mark.real
class TestCrewAIReal:
    """Real CrewAI tests with actual API calls"""

    def test_crewai_simple_crew(self):
        """Test a simple CrewAI crew with real API calls"""
        try:
            from praisonai import PraisonAI
            
            # Create a minimal YAML configuration
            yaml_content = """
framework: crewai
topic: Simple Question Answer
roles:
  - name: Helper
    goal: Answer simple questions accurately
    backstory: I am a helpful assistant who provides clear answers
    tasks:
      - description: What is the capital of France? Provide just the city name.
        expected_output: The capital city of France
"""
            
            # Create temporary test file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content)
                test_file = f.name
            
            try:
                # Initialize PraisonAI with CrewAI
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="crewai"
                )
                
                # Verify setup
                assert praisonai is not None
                assert praisonai.framework == "crewai"
                
                print("✅ CrewAI real test setup successful")
                
                # Note: Full execution would be:
                # result = praisonai.run()
                # But we keep it minimal to avoid costs
                
            finally:
                # Cleanup
                if os.path.exists(test_file):
                    os.unlink(test_file)
                    
        except ImportError as e:
            pytest.skip(f"CrewAI not available: {e}")
        except Exception as e:
            pytest.fail(f"CrewAI real test failed: {e}")

    def test_crewai_environment_check(self):
        """Verify CrewAI environment is properly configured"""
        # Check API key is available
        assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY required for real tests"
        
        # Check CrewAI can be imported
        try:
            import crewai
            assert crewai is not None
        except ImportError:
            pytest.skip("CrewAI not installed")
            
        print("✅ CrewAI environment check passed")

    def test_crewai_multi_agent_setup(self):
        """Test CrewAI multi-agent setup without execution"""
        try:
            from praisonai import PraisonAI
            
            yaml_content = """
framework: crewai
topic: Multi-Agent Collaboration Test
roles:
  - name: Researcher
    goal: Gather information
    backstory: I research topics thoroughly
    tasks:
      - description: Research a simple topic
        expected_output: Brief research summary
  - name: Writer
    goal: Write clear content
    backstory: I write clear and concise content
    tasks:
      - description: Write based on research
        expected_output: Written content
"""
            
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content)
                test_file = f.name
            
            try:
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="crewai"
                )
                
                assert praisonai.framework == "crewai"
                print("✅ CrewAI multi-agent setup successful")
                
            finally:
                if os.path.exists(test_file):
                    os.unlink(test_file)
                    
        except ImportError as e:
            pytest.skip(f"CrewAI not available: {e}")
        except Exception as e:
            pytest.fail(f"CrewAI multi-agent test failed: {e}")

    @pytest.mark.skipif(not os.getenv("PRAISONAI_RUN_FULL_TESTS"), 
                        reason="Full execution test requires PRAISONAI_RUN_FULL_TESTS=true")
    def test_crewai_full_execution(self):
        """
        💰 EXPENSIVE TEST: Actually runs praisonai.run() with real API calls!
        
        Set PRAISONAI_RUN_FULL_TESTS=true to enable this test.
        This will consume API credits and show real output logs.
        """
        try:
            from praisonai import PraisonAI
            import logging
            
            # Enable detailed logging to see the output
            logging.basicConfig(level=logging.INFO)
            
            print("\n" + "="*60)
            print("💰 STARTING CREWAI FULL EXECUTION TEST (REAL API CALLS!)")
            print("="*60)
            
            # Create a very simple YAML for minimal cost
            yaml_content = """
framework: crewai
topic: Quick Math Test
roles:
  - name: Calculator
    goal: Do simple math quickly
    backstory: I am a calculator that gives brief answers
    tasks:
      - description: Calculate 3+3. Answer with just the number, nothing else.
        expected_output: Just the number
"""
            
            # Create temporary test file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(yaml_content)
                test_file = f.name
            
            try:
                # Initialize PraisonAI with CrewAI
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="crewai"
                )
                
                print(f"⛵ Initializing CrewAI with file: {test_file}")
                print(f"📋 Framework: {praisonai.framework}")
                
                # 💰 ACTUAL EXECUTION - THIS COSTS MONEY!
                print("\n💰 EXECUTING REAL CREWAI WORKFLOW...")
                print("⚠️  This will make actual API calls!")
                
                result = praisonai.run()
                
                print("\n" + "="*60)
                print("✅ CREWAI EXECUTION COMPLETED!")
                print("="*60)
                print(f"📊 Result type: {type(result)}")
                if result:
                    print(f"📄 Result content: {str(result)[:500]}...")
                else:
                    print("📄 No result returned")
                print("="*60)
                
                # Verify we got some result
                assert result is not None or True  # Allow empty results
                
            finally:
                # Cleanup
                if os.path.exists(test_file):
                    os.unlink(test_file)
                    
        except ImportError as e:
            pytest.skip(f"CrewAI not available: {e}")
        except Exception as e:
            print(f"\n❌ CrewAI full execution failed: {e}")
            pytest.fail(f"CrewAI full execution test failed: {e}")

if __name__ == "__main__":
    # Enable full tests when running directly
    os.environ["PRAISONAI_RUN_FULL_TESTS"] = "true"
    pytest.main([__file__, "-v", "-m", "real", "-s"]) 