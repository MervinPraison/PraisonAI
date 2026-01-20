"""
EmbeddingResult dataclass for embedding responses.

This module provides a structured result type for embedding operations,
matching the OpenAI embedding response format.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class EmbeddingResult:
    """Result from embedding generation.
    
    Attributes:
        embeddings: List of embedding vectors (each is a list of floats)
        model: The model used for embedding (optional)
        usage: Token usage information (optional)
        metadata: Additional metadata (optional)
    
    Example:
        >>> result = EmbeddingResult(
        ...     embeddings=[[0.1, 0.2, 0.3]],
        ...     model="text-embedding-3-small",
        ...     usage={"prompt_tokens": 5, "total_tokens": 5}
        ... )
        >>> print(len(result.embeddings[0]))
        3
    """
    embeddings: List[List[float]]
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __len__(self) -> int:
        """Return the number of embeddings."""
        return len(self.embeddings)
    
    def __getitem__(self, index: int) -> List[float]:
        """Get embedding by index."""
        return self.embeddings[index]
