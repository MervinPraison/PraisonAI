"""
EmbeddingAgent - A specialized agent for generating text embeddings.

This agent provides embedding capabilities for text using AI embedding models,
with support for batch processing and similarity calculations.

Follows the Agent() class patterns with:
- Lazy loading for heavy dependencies (litellm, rich)
- Precedence Ladder for configuration resolution
- Both sync and async methods
"""

import os
import logging
import math
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, List

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """
    Configuration for embedding settings.
    
    Follows the Precedence Ladder pattern:
    - Instance > Config > Array > Dict > String > Bool > Default
    """
    dimensions: Optional[int] = None
    encoding_format: str = "float"  # float or base64
    timeout: int = 60
    
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LiteLLM calls."""
        return {
            "dimensions": self.dimensions,
            "encoding_format": self.encoding_format,
            "timeout": self.timeout,
            "api_base": self.api_base,
            "api_key": self.api_key,
        }


class EmbeddingAgent:
    """
    A specialized agent for generating text embeddings.
    
    Provides:
    - Single text embedding
    - Batch text embedding
    - Similarity calculation between texts
    
    Supported Providers:
        - OpenAI: `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`
        - Azure: `azure/text-embedding-3-small`
        - Cohere: `cohere/embed-english-v3.0`, `cohere/embed-multilingual-v3.0`
        - Voyage: `voyage/voyage-3`, `voyage/voyage-3-lite`
        - Mistral: `mistral/mistral-embed`
    
    Example:
        ```python
        from praisonaiagents import EmbeddingAgent
        
        # Simple usage
        agent = EmbeddingAgent()
        embedding = agent.embed("Hello world")
        print(f"Embedding dimension: {len(embedding)}")
        
        # Batch embedding
        embeddings = agent.embed_batch([
            "First text",
            "Second text",
            "Third text"
        ])
        
        # Calculate similarity
        score = agent.similarity("Hello", "Hi there")
        print(f"Similarity: {score:.2f}")
        ```
    """
    
    DEFAULT_MODEL = "text-embedding-3-small"
    
    def __init__(
        self,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        embedding: Optional[Union[bool, Dict, "EmbeddingConfig"]] = None,
        verbose: Union[bool, int] = True,
    ):
        """Initialize EmbeddingAgent.
        
        Args:
            name: Agent name for identification
            instructions: Optional instructions (unused for embeddings)
            llm: Model name (e.g., "text-embedding-3-small")
            model: Alias for llm= parameter
            base_url: Custom API endpoint URL
            api_key: API key for the provider
            embedding: Embedding configuration. Accepts:
                - bool: True enables with defaults
                - dict: {"dimensions": 1536}
                - EmbeddingConfig: Full configuration object
            verbose: Verbosity level for output
        """
        if llm is None and model is not None:
            llm = model
        
        self.name = name or "EmbeddingAgent"
        self.instructions = instructions
        self.llm = llm or os.getenv('PRAISONAI_EMBEDDING_MODEL', self.DEFAULT_MODEL)
        self.base_url = base_url
        self.api_key = api_key
        self._embedding_config = self._resolve_embedding_config(embedding)
        self.verbose = verbose
        
        self._litellm = None
        self._console = None
        
        self._configure_logging(verbose)
    
    def _resolve_embedding_config(self, embedding: Optional[Union[bool, Dict, EmbeddingConfig]]) -> EmbeddingConfig:
        """Resolve embedding parameter using Precedence Ladder."""
        if embedding is None or embedding is True or embedding is False:
            return EmbeddingConfig()
        elif isinstance(embedding, EmbeddingConfig):
            return embedding
        elif isinstance(embedding, dict):
            return EmbeddingConfig(**embedding)
        return EmbeddingConfig()
    
    @property
    def console(self):
        """Lazily initialize Rich Console."""
        if self._console is None:
            from rich.console import Console
            self._console = Console()
        return self._console
    
    @property
    def litellm(self):
        """Lazy load litellm module when needed."""
        if self._litellm is None:
            try:
                import litellm
                litellm.telemetry = False
                litellm.success_callback = []
                self._litellm = litellm
            except ImportError:
                raise ImportError(
                    "litellm is required for embedding generation. "
                    "Please install with: pip install litellm"
                )
        return self._litellm
    
    def _configure_logging(self, verbose: Union[bool, int]) -> None:
        """Configure logging levels."""
        if isinstance(verbose, int) and verbose >= 10:
            logging.getLogger("litellm").setLevel(logging.DEBUG)
        else:
            logging.getLogger("litellm").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
    
    def _get_model_params(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Build parameters for LiteLLM calls."""
        params = {"model": model or self.llm}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["api_base"] = self.base_url
        if self._embedding_config.dimensions:
            params["dimensions"] = self._embedding_config.dimensions
        if self._embedding_config.encoding_format != "float":
            params["encoding_format"] = self._embedding_config.encoding_format
        return params
    
    def embed(
        self,
        text: str,
        model: Optional[str] = None,
        **kwargs
    ) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            model: Override model for this call
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of floats representing the embedding vector
            
        Example:
            ```python
            agent = EmbeddingAgent()
            embedding = agent.embed("Hello world")
            print(f"Dimension: {len(embedding)}")
            ```
        """
        params = self._get_model_params(model)
        params["input"] = [text]
        params.update(kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Generating embedding with {params['model']}...[/cyan]")
        
        response = self.litellm.embedding(**params)
        result = response.data[0]["embedding"]
        
        if self.verbose:
            self.console.print(f"[green]✓ Embedding generated (dim={len(result)})[/green]")
        
        return result
    
    def embed_batch(
        self,
        texts: List[str],
        model: Optional[str] = None,
        **kwargs
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            model: Override model for this call
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of embedding vectors
            
        Example:
            ```python
            agent = EmbeddingAgent()
            embeddings = agent.embed_batch(["Hello", "World"])
            print(f"Generated {len(embeddings)} embeddings")
            ```
        """
        if not texts:
            return []
        
        params = self._get_model_params(model)
        params["input"] = texts
        params.update(kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Generating {len(texts)} embeddings with {params['model']}...[/cyan]")
        
        response = self.litellm.embedding(**params)
        results = [item["embedding"] for item in response.data]
        
        if self.verbose:
            self.console.print(f"[green]✓ {len(results)} embeddings generated[/green]")
        
        return results
    
    def similarity(
        self,
        text1: str,
        text2: str,
        model: Optional[str] = None,
        **kwargs
    ) -> float:
        """
        Calculate cosine similarity between two texts.
        
        Args:
            text1: First text
            text2: Second text
            model: Override model for this call
            **kwargs: Additional parameters
            
        Returns:
            Cosine similarity score (0.0 to 1.0)
            
        Example:
            ```python
            agent = EmbeddingAgent()
            score = agent.similarity("Hello", "Hi there")
            print(f"Similarity: {score:.2f}")
            ```
        """
        embeddings = self.embed_batch([text1, text2], model=model, **kwargs)
        return self._cosine_similarity(embeddings[0], embeddings[1])
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            raise ValueError("Vectors must have the same dimension")
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def find_most_similar(
        self,
        query: str,
        candidates: List[str],
        top_k: int = 5,
        model: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Find the most similar texts to a query.
        
        Args:
            query: Query text
            candidates: List of candidate texts to compare
            top_k: Number of top results to return
            model: Override model for this call
            **kwargs: Additional parameters
            
        Returns:
            List of dicts with 'text', 'score', and 'index' keys
            
        Example:
            ```python
            agent = EmbeddingAgent()
            results = agent.find_most_similar(
                "What is AI?",
                ["Artificial intelligence is...", "Machine learning...", "Deep learning..."],
                top_k=2
            )
            for r in results:
                print(f"{r['score']:.2f}: {r['text'][:50]}...")
            ```
        """
        if not candidates:
            return []
        
        all_texts = [query] + candidates
        embeddings = self.embed_batch(all_texts, model=model, **kwargs)
        
        query_embedding = embeddings[0]
        candidate_embeddings = embeddings[1:]
        
        scores = []
        for i, emb in enumerate(candidate_embeddings):
            score = self._cosine_similarity(query_embedding, emb)
            scores.append({
                "text": candidates[i],
                "score": score,
                "index": i
            })
        
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]
    
    async def aembed(
        self,
        text: str,
        model: Optional[str] = None,
        **kwargs
    ) -> List[float]:
        """Async version of embed()."""
        params = self._get_model_params(model)
        params["input"] = [text]
        params.update(kwargs)
        
        response = await self.litellm.aembedding(**params)
        return response.data[0]["embedding"]
    
    async def aembed_batch(
        self,
        texts: List[str],
        model: Optional[str] = None,
        **kwargs
    ) -> List[List[float]]:
        """Async version of embed_batch()."""
        if not texts:
            return []
        
        params = self._get_model_params(model)
        params["input"] = texts
        params.update(kwargs)
        
        response = await self.litellm.aembedding(**params)
        return [item["embedding"] for item in response.data]
    
    async def asimilarity(
        self,
        text1: str,
        text2: str,
        model: Optional[str] = None,
        **kwargs
    ) -> float:
        """Async version of similarity()."""
        embeddings = await self.aembed_batch([text1, text2], model=model, **kwargs)
        return self._cosine_similarity(embeddings[0], embeddings[1])
