from praisonai import PraisonAI

def main():
    praisonai = PraisonAI(agent_file="agents.yaml")
    return praisonai.run()

if __name__ == "__main__":
    print(main())