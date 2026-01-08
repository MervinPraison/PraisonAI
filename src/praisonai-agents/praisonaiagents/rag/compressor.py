"""
Contextual Compression for PraisonAI Agents (Phase 5).

Provides context compression to fit within token budgets:
- Redundancy removal / deduplication
- Query-relevant sentence extraction
- LLM-based summarization fallback

No heavy imports at module level.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class CompressorProtocol(Protocol):
    """Protocol for compression implementations."""
    
    def compress(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        target_tokens: int,
    ) -> List[Dict[str, Any]]:
        """Compress chunks to fit target token budget."""
        ...


@dataclass
class CompressionResult:
    """Result of compression operation."""
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 1.0
    method_used: str = "none"


def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token)."""
    if not text:
        return 0
    return len(text) // 4 + 1


class ContextCompressor:
    """
    Compresses retrieved context to fit within token budget.
    
    Compression strategies (applied in order):
    1. Deduplication - remove redundant chunks
    2. Sentence extraction - keep query-relevant sentences
    3. Truncation - cut to fit budget
    4. Summarization - LLM fallback (optional)
    """
    
    def __init__(
        self,
        llm=None,
        similarity_threshold: float = 0.85,
        verbose: bool = False,
    ):
        """
        Initialize compressor.
        
        Args:
            llm: Optional LLM for summarization fallback
            similarity_threshold: Threshold for deduplication
            verbose: Enable verbose logging
        """
        self._llm = llm
        self._similarity_threshold = similarity_threshold
        self._verbose = verbose
    
    def compress(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        target_tokens: int,
        compression_ratio: float = 0.5,
    ) -> CompressionResult:
        """
        Compress chunks to fit target token budget.
        
        Args:
            chunks: List of chunks with 'text' and 'metadata'
            query: Original query for relevance scoring
            target_tokens: Target token budget
            compression_ratio: Target compression ratio (0.5 = 50% reduction)
            
        Returns:
            CompressionResult with compressed chunks
        """
        result = CompressionResult()
        
        if not chunks:
            return result
        
        # Calculate original tokens
        result.original_tokens = sum(
            estimate_tokens(c.get('text', '')) for c in chunks
        )
        
        # Step 1: Deduplicate
        deduped = self._deduplicate(chunks)
        
        # Step 2: Extract relevant sentences
        extracted = self._extract_relevant(deduped, query)
        
        # Step 3: Truncate to fit budget
        truncated = self._truncate_to_budget(extracted, target_tokens)
        
        # Calculate compressed tokens
        result.compressed_tokens = sum(
            estimate_tokens(c.get('text', '')) for c in truncated
        )
        
        if result.original_tokens > 0:
            result.compression_ratio = result.compressed_tokens / result.original_tokens
        
        result.chunks = truncated
        result.method_used = "dedupe+extract+truncate"
        
        return result
    
    def _deduplicate(
        self,
        chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Remove duplicate or near-duplicate chunks."""
        if not chunks:
            return []
        
        seen_texts = set()
        unique = []
        
        for chunk in chunks:
            text = chunk.get('text', '').strip()
            
            # Skip empty
            if not text:
                continue
            
            # Simple dedup by exact match
            text_key = text[:200].lower()  # First 200 chars as key
            if text_key in seen_texts:
                continue
            
            seen_texts.add(text_key)
            unique.append(chunk)
        
        return unique
    
    def _extract_relevant(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
    ) -> List[Dict[str, Any]]:
        """Extract query-relevant sentences from chunks."""
        if not chunks or not query:
            return chunks
        
        query_words = set(query.lower().split())
        extracted = []
        
        for chunk in chunks:
            text = chunk.get('text', '')
            
            # Split into sentences
            sentences = self._split_sentences(text)
            
            # Score sentences by relevance
            relevant_sentences = []
            for sentence in sentences:
                sentence_words = set(sentence.lower().split())
                overlap = len(query_words & sentence_words)
                
                # Keep sentences with any overlap or important ones
                if overlap > 0 or len(sentence) > 50:
                    relevant_sentences.append(sentence)
            
            # Reconstruct text from relevant sentences
            if relevant_sentences:
                extracted.append({
                    **chunk,
                    'text': ' '.join(relevant_sentences),
                    'metadata': {
                        **chunk.get('metadata', {}),
                        '_compressed': True,
                    },
                })
        
        return extracted
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        import re
        
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _truncate_to_budget(
        self,
        chunks: List[Dict[str, Any]],
        target_tokens: int,
    ) -> List[Dict[str, Any]]:
        """Truncate chunks to fit token budget."""
        if not chunks:
            return []
        
        result = []
        used_tokens = 0
        
        for chunk in chunks:
            text = chunk.get('text', '')
            chunk_tokens = estimate_tokens(text)
            
            if used_tokens + chunk_tokens <= target_tokens:
                result.append(chunk)
                used_tokens += chunk_tokens
            else:
                # Partial fit
                remaining = target_tokens - used_tokens
                if remaining > 50:  # Only if meaningful space
                    chars_to_keep = remaining * 4
                    truncated_text = text[:chars_to_keep] + "..."
                    result.append({
                        **chunk,
                        'text': truncated_text,
                        'metadata': {
                            **chunk.get('metadata', {}),
                            '_truncated': True,
                        },
                    })
                break
        
        return result
    
    def summarize(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        target_tokens: int,
    ) -> str:
        """
        Summarize chunks using LLM (fallback method).
        
        Args:
            chunks: Chunks to summarize
            query: Original query for context
            target_tokens: Target token budget
            
        Returns:
            Summarized text
        """
        if not self._llm or not chunks:
            return ""
        
        # Combine chunk texts
        combined = "\n\n".join(c.get('text', '') for c in chunks)
        
        # Create summarization prompt
        prompt = f"""Summarize the following content to answer this query: {query}

Content:
{combined}

Provide a concise summary that captures the key information relevant to the query.
Keep the summary under {target_tokens * 4} characters."""
        
        try:
            response = self._llm.generate(prompt)
            return response if isinstance(response, str) else str(response)
        except Exception:
            return combined[:target_tokens * 4]
