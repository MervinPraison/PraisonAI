from praisonaiagents import OCRAgent

agent = OCRAgent()

# Extract with page selection (pages is 0-indexed)
result = agent.extract("https://arxiv.org/pdf/2201.04234", pages=[0, 1])
for page in result.pages:
    print(f"Page {page.index}: {page.markdown[:200]}")

# Quick read - just get the text
text = agent.read("https://arxiv.org/pdf/2201.04234")
print(f"Total length: {len(text)} chars")
