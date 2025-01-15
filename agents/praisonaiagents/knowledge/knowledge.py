class Knowledge:
    def __init__(self, config=None):
        try:
            from mem0 import Memory
        except ImportError:
            raise ImportError(
                "knowledge is not installed. Please install it using: "
                'pip install "praisonaiagents[knowledge]"'
            )

        self.config = config or {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test",
                    "path": ".praison",
                }
            }
        }

        m = Memory.from_config(self.config)
        self.memory = m

    def store(self, content, user_id=None, agent_id=None, run_id=None, metadata=None):
        """
        Store a memory.
        
        Args:
            content (str): The content of the memory.
            user_id (str, optional): The user ID associated with the memory.
            agent_id (str, optional): The agent ID associated with the memory.
            run_id (str, optional): The run ID associated with the memory.
            metadata (dict, optional): Additional metadata for the memory.

        Returns:
            dict: The result of storing the memory.
        """
        return self.memory.add(content, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)

    def get_all(self, user_id=None, agent_id=None, run_id=None):
        """
        Retrieve all memories.
        
        Args:
            user_id (str, optional): The user ID to filter memories by.
            agent_id (str, optional): The agent ID to filter memories by.
            run_id (str, optional): The run ID to filter memories by.

        Returns:
            list: All memories matching the specified filters.
        """
        return self.memory.get_all(user_id=user_id, agent_id=agent_id, run_id=run_id)

    def get(self, memory_id):
        """
        Retrieve a specific memory by ID.
        
        Args:
            memory_id (str): The ID of the memory to retrieve.

        Returns:
            dict: The retrieved memory.
        """
        return self.memory.get(memory_id)

    def search(self, query, user_id=None, agent_id=None, run_id=None):
        """
        Search for memories related to a query.
        
        Args:
            query (str): The search query.
            user_id (str, optional): The user ID to filter memories by.
            agent_id (str, optional): The agent ID to filter memories by.
            run_id (str, optional): The run ID to filter memories by.

        Returns:
            list: Memories related to the search query.
        """
        return self.memory.search(query, user_id=user_id, agent_id=agent_id, run_id=run_id)

    def update(self, memory_id, data):
        """
        Update a memory.
        
        Args:
            memory_id (str): The ID of the memory to update.
            data (str): The updated content of the memory.

        Returns:
            dict: The result of updating the memory.
        """
        return self.memory.update(memory_id, data)

    def history(self, memory_id):
        """
        Get the history of changes for a memory.
        
        Args:
            memory_id (str): The ID of the memory.

        Returns:
            list: The history of changes for the memory.
        """
        return self.memory.history(memory_id)

    def delete(self, memory_id):
        """
        Delete a memory.
        
        Args:
            memory_id (str): The ID of the memory to delete.
        """
        self.memory.delete(memory_id)

    def delete_all(self, user_id=None, agent_id=None, run_id=None):
        """
        Delete all memories.
        
        Args:
            user_id (str, optional): The user ID to filter memories by.
            agent_id (str, optional): The agent ID to filter memories by.
            run_id (str, optional): The run ID to filter memories by.
        """
        self.memory.delete_all(user_id=user_id, agent_id=agent_id, run_id=run_id)

    def reset(self):
        """Reset all memories."""
        self.memory.reset()