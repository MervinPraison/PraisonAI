import logging
from praisonaiagents.knowledge import Knowledge
import os
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "test",
            "path": ".praison",
        }
    }
}

knowledge = Knowledge(config)

# Store memories
logger.info("Storing memories...")
cricket_memory = knowledge.store("Likes to play cricket on weekends", user_id="alice", metadata={"category": "hobbies"})
logger.info(f"Stored cricket memory: {cricket_memory}")
tennis_memory = knowledge.store("Enjoys playing tennis with friends", user_id="alice", metadata={"category": "hobbies"})
logger.info(f"Stored tennis memory: {tennis_memory}")
work_memory = knowledge.store("Works as a software engineer", user_id="alice", metadata={"category": "work"})
logger.info(f"Stored work memory: {work_memory}")

print("Stored memories:")
print(cricket_memory)
print(tennis_memory)
print(work_memory)

# Retrieve all memories for a user
logger.info("Retrieving all memories for Alice...")
alice_memories = knowledge.get_all(user_id="alice")
logger.info(f"Retrieved memories for Alice: {alice_memories}")
print("\nAll memories for Alice:")
for memory in alice_memories:
    print(memory)

# Retrieve a specific memory by ID
logger.info(f"Retrieving memory with ID: {cricket_memory['results'][0]['id']}")
retrieved_memory = knowledge.get(cricket_memory['results'][0]["id"])
logger.info(f"Retrieved memory: {retrieved_memory}")
print("\nRetrieved memory:")
print(retrieved_memory)

# Search for memories based on a query
query = "What are Alice's hobbies?"
logger.info(f"Searching for memories with query: {query}")
search_results = knowledge.search(query, user_id="alice")
logger.info(f"Search results: {search_results}")
print(f"\nSearch results for '{query}':")
for memory in search_results:
    print(memory)

# Update a memory
logger.info(f"Updating memory with ID: {tennis_memory['results'][0]['id']}")
updated_memory = knowledge.update(memory_id=tennis_memory['results'][0]["id"], data="Loves playing tennis on weekends")
logger.info(f"Updated memory: {updated_memory}")
print("\nUpdated memory:")
print(updated_memory)

# Get memory history
logger.info(f"Retrieving memory history for ID: {tennis_memory['results'][0]['id']}")
memory_history = knowledge.history(memory_id=tennis_memory['results'][0]["id"])
logger.info(f"Memory history: {memory_history}")
print("\nMemory history:")
for entry in memory_history:
    print(entry)

# Delete a memory
logger.info(f"Deleting memory with ID: {work_memory['results'][0]['id']}")
knowledge.delete(memory_id=work_memory['results'][0]["id"])
logger.info("Memory deleted")
print("\nDeleted memory")

# Retrieve memories after deletion
logger.info("Retrieving memories after deletion...")
alice_memories = knowledge.get_all(user_id="alice")
logger.info(f"Retrieved memories after deletion: {alice_memories}")
print("\nMemories after deletion:")
for memory in alice_memories:
    print(memory)

# Delete all memories for a user
logger.info("Deleting all memories for Alice...")
knowledge.delete_all(user_id="alice")
logger.info("All memories for Alice deleted")
print("\nAll memories for Alice deleted")

# Retrieve memories after deleting all
logger.info("Retrieving memories after deleting all...")
alice_memories = knowledge.get_all(user_id="alice")
logger.info(f"Retrieved memories after deleting all: {alice_memories}")
print("\nMemories after deleting all:")
print(alice_memories)

# Reset all memories
logger.info("Resetting all memories...")
knowledge.reset()
logger.info("All memories reset")
print("\nAll memories reset")

# Test file handling
logger.info("Testing file handling...")

try:
    # Get absolute path to test files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_file = os.path.join(current_dir, "small.pdf")
    txt_file = os.path.join(current_dir, "sample.txt")

    # Test text file
    logger.info(f"Testing text file: {txt_file}")
    # Read and display content
    with open(txt_file, 'r') as file:
        txt_content = file.read()
        print("\nText file content:")
        print(txt_content)
    # Store the text file using add
    txt_memory = knowledge.add(txt_file, user_id="bob", metadata={"type": "text"})
    logger.info(f"Stored text file: {txt_memory}")
    print("\nStored text content:")
    if txt_memory and 'results' in txt_memory and txt_memory['results']:
        for mem in txt_memory['results']:
            print(mem)
    else:
        print("No valid memories were stored from the text file")

    # Verify text memories are stored
    if txt_memory and 'results' in txt_memory and txt_memory['results']:
        logger.info("Verifying text memories...")
        for mem in txt_memory['results']:
            if isinstance(mem, dict) and 'id' in mem:
                stored = knowledge.get(mem['id'])
                logger.info(f"Verified text memory: {stored}")
            else:
                logger.warning(f"Unexpected memory format: {mem}")
    else:
        logger.warning("No valid memories were stored from the text file")

    # Test pdf file
    logger.info(f"Testing pdf file: {pdf_file}")
    pdf_memory = knowledge.add(pdf_file, user_id="bob", metadata={"type": "pdf"})
    logger.info(f"Stored pdf file: {pdf_memory}")
    print("\nStored pdf content:")
    if pdf_memory and 'results' in pdf_memory and pdf_memory['results']:
        for mem in pdf_memory['results']:
            print(mem)
    else:
        print("No valid memories were stored from the PDF file")

    # Verify stored content
    if pdf_memory and 'results' in pdf_memory and pdf_memory['results']:
        for memory in pdf_memory['results']:
            if isinstance(memory, dict) and 'id' in memory:
                stored_memory = knowledge.get(memory['id'])
                logger.info(f"Verified stored memory: {stored_memory}")
                print("\nVerified content:")
                print(stored_memory)
            else:
                logger.warning(f"Unexpected memory format: {memory}")
    else:
        logger.warning("No valid memories were stored from the PDF file")

except Exception as e:
    logger.error(f"Error during file handling test: {str(e)}")
    raise

