from praisonaiagents import ContextAgent

agent = ContextAgent(llm="gpt-5-nano", auto_analyze=False)

agent.start("https://github.com/MervinPraison/PraisonAI/ Need to add Authentication")