from praisonaiagents import OCRAgent

agent = OCRAgent(llm="mistral/mistral-ocr-latest")
text = agent.read("document.pdf")
print(text)
