from typing import List, Union, Optional, Dict, Any
from functools import cached_property
import importlib

class Chunking:
    """A unified class for text chunking with various chunking strategies."""
    
    CHUNKER_PARAMS = {
        'token': ['chunk_size', 'chunk_overlap', 'tokenizer'],
        'word': ['chunk_size', 'chunk_overlap', 'tokenizer'],
        'sentence': ['chunk_size', 'chunk_overlap', 'tokenizer'],
        'semantic': ['chunk_size', 'embedding_model', 'tokenizer'],
        'sdpm': ['chunk_size', 'embedding_model', 'tokenizer'],
        'late': ['chunk_size', 'embedding_model', 'tokenizer'],
        'recursive': ['chunk_size', 'tokenizer']
    }
    
    @cached_property
    def SUPPORTED_CHUNKERS(self) -> Dict[str, Any]:
        """Lazy load chunker classes."""
        try:
            from chonkie.chunker import (
                TokenChunker,
                WordChunker,
                SentenceChunker,
                SemanticChunker,
                SDPMChunker,
                LateChunker,
                RecursiveChunker
            )
        except ImportError:
            raise ImportError(
                "chonkie package not found. Please install it using: pip install 'praisonaiagents[knowledge]'"
            )
            
        return {
            'token': TokenChunker,
            'word': WordChunker,
            'sentence': SentenceChunker,
            'semantic': SemanticChunker,
            'sdpm': SDPMChunker,
            'late': LateChunker,
            'recursive': RecursiveChunker
        }

    def __init__(
        self,
        chunker_type: str = 'token',
        chunk_size: int = 512,
        chunk_overlap: int = 128,
        tokenizer: str = "gpt2",
        embedding_model: Optional[Union[str, Any]] = None,
        **kwargs
    ):
        """Initialize the Chunking class."""
        if chunker_type not in self.CHUNKER_PARAMS:
            raise ValueError(
                f"Unsupported chunker type: {chunker_type}. "
                f"Must be one of: {list(self.CHUNKER_PARAMS.keys())}"
            )
        
        self.chunker_type = chunker_type
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tokenizer
        self._embedding_model = embedding_model
        self.kwargs = kwargs
        
        # Initialize these as None for lazy loading
        self._chunker = None
        self._embeddings = None
        
    @cached_property
    def embedding_model(self):
        """Lazy load the embedding model."""
        if self._embedding_model is None and self.chunker_type in ['semantic', 'sdpm', 'late']:
            from chonkie.embeddings import AutoEmbeddings
            return AutoEmbeddings.get_embeddings("all-MiniLM-L6-v2")
        elif isinstance(self._embedding_model, str):
            from chonkie.embeddings import AutoEmbeddings
            return AutoEmbeddings.get_embeddings(self._embedding_model)
        return self._embedding_model

    def _get_chunker_params(self) -> Dict[str, Any]:
        """Get the appropriate parameters for the current chunker type."""
        allowed_params = self.CHUNKER_PARAMS[self.chunker_type]
        params = {'chunk_size': self.chunk_size}
        
        if 'chunk_overlap' in allowed_params:
            params['chunk_overlap'] = self.chunk_overlap
            
        if 'tokenizer' in allowed_params:
            if self.chunker_type in ['semantic', 'sdpm', 'late']:
                params['tokenizer'] = self.embedding_model.get_tokenizer_or_token_counter()
            else:
                params['tokenizer'] = self.tokenizer
                
        if 'embedding_model' in allowed_params:
            params['embedding_model'] = self.embedding_model
            
        # Add any additional kwargs that are in allowed_params
        for key, value in self.kwargs.items():
            if key in allowed_params:
                params[key] = value
                
        return params

    @cached_property
    def chunker(self):
        """Lazy load the chunker instance."""
        if self._chunker is None:
            chunker_cls = self.SUPPORTED_CHUNKERS[self.chunker_type]
            common_params = self._get_chunker_params()
            self._chunker = chunker_cls(**common_params)
        
        return self._chunker
    
    def _get_overlap_refinery(self, context_size: Optional[int] = None, **kwargs):
        """Lazy load the overlap refinery."""
        try:
            from chonkie.refinery import OverlapRefinery
        except ImportError:
            raise ImportError("Failed to import OverlapRefinery from chonkie.refinery")
            
        if context_size is None:
            context_size = self.chunk_overlap
            
        return OverlapRefinery(
            context_size=context_size,
            tokenizer=self.chunker.tokenizer,
            **kwargs
        )
    
    def add_overlap_context(
        self,
        chunks: List[Any],
        context_size: int = None,
        mode: str = "suffix",
        merge_context: bool = True
    ) -> List[Any]:
        """Add overlap context to chunks using OverlapRefinery."""
        refinery = self._get_overlap_refinery(
            context_size=context_size,
            mode=mode,
            merge_context=merge_context
        )
        return refinery.refine(chunks)
    
    def chunk(
        self,
        text: Union[str, List[str]],
        add_context: bool = False,
        context_params: Optional[Dict[str, Any]] = None
    ) -> Union[List[Any], List[List[Any]]]:
        """Chunk text using the configured chunking strategy."""
        chunks = self.chunker(text)
        
        if add_context:
            context_params = context_params or {}
            if isinstance(text, str):
                chunks = self.add_overlap_context(chunks, **context_params)
            else:
                chunks = [self.add_overlap_context(c, **context_params) for c in chunks]
                
        return chunks
    
    def __call__(
        self,
        text: Union[str, List[str]],
        add_context: bool = False,
        context_params: Optional[Dict[str, Any]] = None
    ) -> Union[List[Any], List[List[Any]]]:
        """Make the Chunking instance callable."""
        return self.chunk(text, add_context, context_params)
    
    def __repr__(self) -> str:
        """String representation of the Chunking instance."""
        return (
            f"Chunking(chunker_type='{self.chunker_type}', "
            f"chunk_size={self.chunk_size}, "
            f"chunk_overlap={self.chunk_overlap})"
        )