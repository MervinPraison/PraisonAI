from praisonai import PraisonAI
    
def advanced():
    praisonai = PraisonAI(
        agent_file="agents.yaml",
        framework="autogen",
    )
    print(praisonai)
    return praisonai.run()

if __name__ == "__main__":
    print(advanced())