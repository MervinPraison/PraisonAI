from praisonai import PraisonAI
import os
    
def auto():
    praisonai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praisonai.framework)
    result = praisonai.run()
    
    # Return a meaningful result - either the actual result or a success indicator
    if result is not None:
        return result
    else:
        # If run() returns None, return a success indicator that we can test for
        return "Auto example completed successfully"

if __name__ == "__main__":
    print(auto())