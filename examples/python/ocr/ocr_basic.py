from praisonaiagents import OCRAgent

agent = OCRAgent()
text = agent.read("document.pdf")
print(text)
