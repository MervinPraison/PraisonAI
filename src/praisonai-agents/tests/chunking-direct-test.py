from praisonaiagents.knowledge import Chunking

# No heavy imports or initialization happens here
chunking = Chunking(chunker_type='token')

# Chunker is only initialized when first used
chunks = chunking.chunk("Your text here")

# Embedding model is only loaded if using semantic chunking
semantic_chunking = Chunking(chunker_type='recursive')
# Embedding model and chunker are loaded here on first use
semantic_chunks = semantic_chunking.chunk("Your text here")

print(semantic_chunks)