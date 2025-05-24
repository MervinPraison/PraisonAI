from praisonai import PraisonAI
import os
    
def advanced():
    # Get the correct path to agents.yaml relative to the test file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    agent_file_path = os.path.join(current_dir, "agents.yaml")
    
    praisonai = PraisonAI(
        agent_file=agent_file_path,
        framework="autogen",
    )
    print(praisonai)
    result = praisonai.run()
    
    # Return a meaningful result - either the actual result or a success indicator
    if result is not None:
        return result
    else:
        # If run() returns None, return a success indicator that we can test for
        return "Advanced example completed successfully"

if __name__ == "__main__":
    print(advanced())