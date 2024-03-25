from praisonai import PraisonAI

def main():
    praison_ai = PraisonAI(agent_file="agents.yaml")
    praison_ai.main()
    
def configuration():
    praison_ai = PraisonAI(
        agent_file="agents.yaml",
        framework="autogen",
    )
    praison_ai.main()
    
def automatic():
    praison_ai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praison_ai.framework)
    praison_ai.main()

if __name__ == "__main__":
    main()
    configuration()
    automatic()