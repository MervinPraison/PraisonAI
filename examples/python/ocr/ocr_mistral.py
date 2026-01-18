from praisonaiagents import OCRAgent

agent = OCRAgent(llm="mistral/mistral-ocr-latest")
text = agent.read("https://arxiv.org/pdf/2201.04234")
print(text[:500])  # First 500 chars
