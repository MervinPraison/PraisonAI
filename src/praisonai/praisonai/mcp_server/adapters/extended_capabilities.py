"""
Extended Capabilities Adapter

Maps additional PraisonAI capabilities to MCP tools:
- Videos
- Files
- Batches
- Vector Stores
- OCR
- Assistants
- Fine-tuning
- A2A
- Containers
- Skills
- Realtime
"""

import logging
from typing import List, Optional

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_extended_capability_tools() -> None:
    """Register extended capability-based MCP tools."""
    
    # Video tools
    @register_tool("praisonai.videos.generate")
    def videos_generate(
        prompt: str,
        model: str = "runway-gen3",
        duration: int = 4,
    ) -> str:
        """Generate video from text prompt."""
        try:
            from praisonai.capabilities import video_generate
            result = video_generate(prompt=prompt, model=model, duration=duration)
            return str(result)
        except ImportError:
            return "Error: Video generation not available"
        except Exception as e:
            return f"Error: {e}"
    
    # File tools
    @register_tool("praisonai.files.create")
    def files_create(
        file_path: str,
        purpose: str = "assistants",
    ) -> str:
        """Upload a file."""
        try:
            from praisonai.capabilities import file_create
            result = file_create(file=file_path, purpose=purpose)
            if hasattr(result, "id"):
                return f"File created: {result.id}"
            return str(result)
        except ImportError:
            return "Error: File operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.files.list")
    def files_list(purpose: Optional[str] = None) -> str:
        """List uploaded files."""
        try:
            from praisonai.capabilities import file_list
            result = file_list(purpose=purpose)
            if hasattr(result, "data"):
                files = [{"id": f.id, "filename": f.filename} for f in result.data]
                return str(files)
            return str(result)
        except ImportError:
            return "Error: File operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.files.retrieve")
    def files_retrieve(file_id: str) -> str:
        """Retrieve file metadata."""
        try:
            from praisonai.capabilities import file_retrieve
            result = file_retrieve(file_id=file_id)
            return str(result)
        except ImportError:
            return "Error: File operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.files.delete")
    def files_delete(file_id: str) -> str:
        """Delete a file."""
        try:
            from praisonai.capabilities import file_delete
            file_delete(file_id=file_id)
            return f"File deleted: {file_id}"
        except ImportError:
            return "Error: File operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.files.content")
    def files_content(file_id: str) -> str:
        """Get file content."""
        try:
            from praisonai.capabilities import file_content
            result = file_content(file_id=file_id)
            return str(result)
        except ImportError:
            return "Error: File operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Batch tools
    @register_tool("praisonai.batches.create")
    def batches_create(
        input_file_id: str,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = "24h",
    ) -> str:
        """Create a batch processing job."""
        try:
            from praisonai.capabilities import batch_create
            result = batch_create(
                input_file_id=input_file_id,
                endpoint=endpoint,
                completion_window=completion_window,
            )
            if hasattr(result, "id"):
                return f"Batch created: {result.id}"
            return str(result)
        except ImportError:
            return "Error: Batch operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.batches.list")
    def batches_list() -> str:
        """List batch jobs."""
        try:
            from praisonai.capabilities import batch_list
            result = batch_list()
            return str(result)
        except ImportError:
            return "Error: Batch operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.batches.retrieve")
    def batches_retrieve(batch_id: str) -> str:
        """Retrieve batch job status."""
        try:
            from praisonai.capabilities import batch_retrieve
            result = batch_retrieve(batch_id=batch_id)
            return str(result)
        except ImportError:
            return "Error: Batch operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.batches.cancel")
    def batches_cancel(batch_id: str) -> str:
        """Cancel a batch job."""
        try:
            from praisonai.capabilities import batch_cancel
            batch_cancel(batch_id=batch_id)
            return f"Batch cancelled: {batch_id}"
        except ImportError:
            return "Error: Batch operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Vector Store tools
    @register_tool("praisonai.vector_stores.create")
    def vector_stores_create(
        name: str,
        file_ids: Optional[List[str]] = None,
    ) -> str:
        """Create a vector store."""
        try:
            from praisonai.capabilities import vector_store_create
            result = vector_store_create(name=name, file_ids=file_ids or [])
            if hasattr(result, "id"):
                return f"Vector store created: {result.id}"
            return str(result)
        except ImportError:
            return "Error: Vector store operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.vector_stores.search")
    def vector_stores_search(
        vector_store_id: str,
        query: str,
        max_results: int = 10,
    ) -> str:
        """Search a vector store."""
        try:
            from praisonai.capabilities import vector_store_search
            result = vector_store_search(
                vector_store_id=vector_store_id,
                query=query,
                max_num_results=max_results,
            )
            return str(result)
        except ImportError:
            return "Error: Vector store operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.vector_stores.file_create")
    def vector_stores_file_create(
        vector_store_id: str,
        file_id: str,
    ) -> str:
        """Add a file to a vector store."""
        try:
            from praisonai.capabilities import vector_store_file_create
            vector_store_file_create(
                vector_store_id=vector_store_id,
                file_id=file_id,
            )
            return f"File {file_id} added to vector store {vector_store_id}"
        except ImportError:
            return "Error: Vector store operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.vector_stores.file_list")
    def vector_stores_file_list(vector_store_id: str) -> str:
        """List files in a vector store."""
        try:
            from praisonai.capabilities import vector_store_file_list
            result = vector_store_file_list(vector_store_id=vector_store_id)
            return str(result)
        except ImportError:
            return "Error: Vector store operations not available"
        except Exception as e:
            return f"Error: {e}"
    
    # OCR tools
    @register_tool("praisonai.ocr")
    def ocr_extract(
        image_path: str,
        model: str = "gpt-4o",
    ) -> str:
        """Extract text from image using OCR."""
        try:
            from praisonai.capabilities import ocr
            result = ocr(file=image_path, model=model)
            return str(result)
        except ImportError:
            return "Error: OCR not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Assistant tools
    @register_tool("praisonai.assistants.create")
    def assistants_create(
        name: str,
        instructions: str,
        model: str = "gpt-4o",
        tools: Optional[List[str]] = None,
    ) -> str:
        """Create an OpenAI-style assistant."""
        try:
            from praisonai.capabilities import assistant_create
            result = assistant_create(
                name=name,
                instructions=instructions,
                model=model,
                tools=tools or [],
            )
            if hasattr(result, "id"):
                return f"Assistant created: {result.id}"
            return str(result)
        except ImportError:
            return "Error: Assistants not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.assistants.list")
    def assistants_list() -> str:
        """List assistants."""
        try:
            from praisonai.capabilities import assistant_list
            result = assistant_list()
            return str(result)
        except ImportError:
            return "Error: Assistants not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Fine-tuning tools
    @register_tool("praisonai.fine_tuning.create")
    def fine_tuning_create(
        training_file: str,
        model: str = "gpt-4o-mini",
        suffix: Optional[str] = None,
    ) -> str:
        """Create a fine-tuning job."""
        try:
            from praisonai.capabilities import fine_tuning_create
            result = fine_tuning_create(
                training_file=training_file,
                model=model,
                suffix=suffix,
            )
            if hasattr(result, "id"):
                return f"Fine-tuning job created: {result.id}"
            return str(result)
        except ImportError:
            return "Error: Fine-tuning not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.fine_tuning.list")
    def fine_tuning_list() -> str:
        """List fine-tuning jobs."""
        try:
            from praisonai.capabilities import fine_tuning_list
            result = fine_tuning_list()
            return str(result)
        except ImportError:
            return "Error: Fine-tuning not available"
        except Exception as e:
            return f"Error: {e}"
    
    # A2A tools
    @register_tool("praisonai.a2a.send")
    def a2a_send(
        agent_url: str,
        message: str,
        task_id: Optional[str] = None,
    ) -> str:
        """Send message to another agent via A2A protocol."""
        try:
            from praisonai.capabilities import a2a_send
            result = a2a_send(
                agent_url=agent_url,
                message=message,
                task_id=task_id,
            )
            return str(result)
        except ImportError:
            return "Error: A2A not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Container tools
    @register_tool("praisonai.containers.create")
    def containers_create(
        name: str,
        image: str = "python:3.11",
    ) -> str:
        """Create a container for code execution."""
        try:
            from praisonai.capabilities import container_create
            result = container_create(name=name, image=image)
            if hasattr(result, "id"):
                return f"Container created: {result.id}"
            return str(result)
        except ImportError:
            return "Error: Containers not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.containers.file_read")
    def containers_file_read(
        container_id: str,
        file_path: str,
    ) -> str:
        """Read a file from a container."""
        try:
            from praisonai.capabilities import container_file_read
            result = container_file_read(
                container_id=container_id,
                file_path=file_path,
            )
            return str(result)
        except ImportError:
            return "Error: Containers not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.containers.file_write")
    def containers_file_write(
        container_id: str,
        file_path: str,
        content: str,
    ) -> str:
        """Write a file to a container."""
        try:
            from praisonai.capabilities import container_file_write
            container_file_write(
                container_id=container_id,
                file_path=file_path,
                content=content,
            )
            return f"File {file_path} written to container {container_id}"
        except ImportError:
            return "Error: Containers not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Skills tools
    @register_tool("praisonai.skills.list")
    def skills_list() -> str:
        """List available skills."""
        try:
            from praisonai.capabilities import skill_list
            result = skill_list()
            return str(result)
        except ImportError:
            return "Error: Skills not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.skills.load")
    def skills_load(skill_path: str) -> str:
        """Load a skill from path."""
        try:
            from praisonai.capabilities import skill_load
            result = skill_load(skill_path=skill_path)
            return str(result)
        except ImportError:
            return "Error: Skills not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Realtime tools
    @register_tool("praisonai.realtime.connect")
    def realtime_connect(
        model: str = "gpt-4o-realtime-preview",
    ) -> str:
        """Connect to realtime API."""
        try:
            from praisonai.capabilities import realtime_connect
            result = realtime_connect(model=model)
            return str(result)
        except ImportError:
            return "Error: Realtime not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.realtime.send")
    def realtime_send(
        session_id: str,
        message: str,
    ) -> str:
        """Send message to realtime session."""
        try:
            from praisonai.capabilities import realtime_send
            result = realtime_send(session_id=session_id, message=message)
            return str(result)
        except ImportError:
            return "Error: Realtime not available"
        except Exception as e:
            return f"Error: {e}"
    
    logger.info("Registered extended capability MCP tools")
