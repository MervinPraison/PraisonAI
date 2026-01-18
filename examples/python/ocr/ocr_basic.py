# OCR with Mistral
# Requires: export MISTRAL_API_KEY=your-key
# Note: Source must be a URL (https://) or base64

from praisonaiagents import OCRAgent

agent = OCRAgent()
text = agent.read("https://arxiv.org/pdf/2201.04234")
print(text[:500])  # First 500 chars
