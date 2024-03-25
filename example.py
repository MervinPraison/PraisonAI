from praisonai import PraisonAI

def basic():
    praison_ai = PraisonAI(agent_file="agents.yaml")
    praison_ai.main()
    
def advanced():
    praison_ai = PraisonAI(
        agent_file="agents.yaml",
        framework="autogen",
    )
    praison_ai.main()
    
def auto():
    praison_ai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praison_ai.framework)
    praison_ai.main()

if __name__ == "__main__":
    basic()
    advanced()
    auto()