from praisonai import PraisonAI
    
def auto():
    praisonai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praisonai.framework)
    return praisonai.run()

if __name__ == "__main__":
    print(auto())