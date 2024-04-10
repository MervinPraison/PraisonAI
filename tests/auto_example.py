from praisonai import PraisonAI
    
def auto():
    praison_ai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praison_ai.framework)
    return praison_ai.main()

if __name__ == "__main__":
    print(auto())