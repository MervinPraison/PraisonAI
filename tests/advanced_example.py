from praisonai import PraisonAI
    
def advanced():
    praison_ai = PraisonAI(
        agent_file="agents.yaml",
        framework="autogen",
    )
    praison_ai.main()

if __name__ == "__main__":
    advanced()