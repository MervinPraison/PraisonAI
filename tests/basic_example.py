from praisonai import PraisonAI
import os

def basic_agent_example():
    # Get the correct path to agents.yaml relative to the test file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    agent_file_path = os.path.join(current_dir, "agents.yaml")
    
    # For fast tests, we don't actually run the LLM calls
    # Just verify that PraisonAI can be instantiated properly
    try:
        praisonai = PraisonAI(agent_file=agent_file_path)
        # Return success without making actual API calls
        return "Basic example setup completed successfully"
    except Exception as e:
        return f"Basic example failed during setup: {e}"

def main():
    return basic_agent_example()

if __name__ == "__main__":
    print(main())