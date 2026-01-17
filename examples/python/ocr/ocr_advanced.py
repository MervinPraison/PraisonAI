from praisonaiagents import OCRAgent

agent = OCRAgent()

# Extract with page selection
result = agent.extract("document.pdf", pages=[1, 2, 3])
for page in result.pages:
    print(f"Page {page.index}: {page.markdown[:100]}")

# From image
text = agent.read("screenshot.png")

# From URL
text = agent.read("https://example.com/doc.pdf")
