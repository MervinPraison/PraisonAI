import logging
from praisonaiagents.knowledge import Knowledge
import os
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

knowledge = Knowledge()
try:
    # Get absolute path to test files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_file = os.path.join(current_dir, "large.pdf")

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