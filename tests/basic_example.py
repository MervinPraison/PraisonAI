from praisonai import PraisonAI

def main():
    praison_ai = PraisonAI(agent_file="agents.yaml")
    return praison_ai.main()

if __name__ == "__main__":
    print(main())