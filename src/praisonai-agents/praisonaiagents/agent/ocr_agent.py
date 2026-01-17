"""
OCRAgent - A specialized agent class for OCR (Optical Character Recognition).
Extracts text from documents and images using AI models.

Follows the Agent() class patterns:
- Precedence Ladder: Instance > Config > Array > Dict > String > Bool > Default
- Lazy imports for LiteLLM (zero overhead until first use)
- Async-safe with both sync and async methods
"""
import os
import logging
import warnings
from dataclasses import dataclass
from typing import Optional, Any, Dict, Union, List
from pathlib import Path

warnings.filterwarnings("ignore", "Valid config keys have changed in V2", UserWarning)


@dataclass
class OCRConfig:
    """Configuration for OCR settings."""
    include_image_base64: bool = False
    pages: Optional[List[int]] = None
    image_limit: Optional[int] = None
    timeout: int = 600
    api_base: Optional[str] = None
    api_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LiteLLM calls."""
        return {
            "include_image_base64": self.include_image_base64,
            "pages": self.pages,
            "image_limit": self.image_limit,
            "timeout": self.timeout,
            "api_base": self.api_base,
            "api_key": self.api_key,
        }


class OCRAgent:
    """
    A specialized agent for OCR (Optical Character Recognition).
    
    Extracts text from documents (PDFs) and images using AI models.
    
    Supported Providers:
        - Mistral: `mistral/mistral-ocr-latest`
    
    Example:
        ```python
        from praisonaiagents import OCRAgent
        
        agent = OCRAgent(llm="mistral/mistral-ocr-latest")
        
        # Extract from PDF URL
        result = agent.extract("https://example.com/document.pdf")
        print(result.text)
        
        # Extract from image URL
        result = agent.extract("https://example.com/image.png")
        for page in result.pages:
            print(page.markdown)
        ```
    """
    
    DEFAULT_MODEL = "mistral/mistral-ocr-latest"
    
    def __init__(
        self,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        ocr: Optional[Union[bool, Dict, "OCRConfig"]] = None,
        verbose: Union[bool, int] = True,
    ):
        """Initialize OCRAgent.
        
        Args:
            name: Agent name for identification
            instructions: Optional instructions
            llm: Model name (e.g., "mistral/mistral-ocr-latest")
            model: Alias for llm= parameter
            base_url: Custom API endpoint URL
            api_key: API key for the provider
            ocr: OCR configuration
            verbose: Verbosity level for output
        """
        if llm is None and model is not None:
            llm = model
        
        self.name = name or "OCRAgent"
        self.instructions = instructions
        self.llm = llm or os.getenv('PRAISONAI_OCR_MODEL', self.DEFAULT_MODEL)
        self.base_url = base_url
        self.api_key = api_key
        self._ocr_config = self._resolve_ocr_config(ocr)
        self.verbose = verbose
        
        self._litellm = None
        self._console = None
        
        self._configure_logging(verbose)
    
    def _resolve_ocr_config(self, ocr: Optional[Union[bool, Dict, OCRConfig]]) -> OCRConfig:
        """Resolve ocr parameter using Precedence Ladder."""
        if ocr is None or ocr is True or ocr is False:
            return OCRConfig()
        elif isinstance(ocr, OCRConfig):
            return ocr
        elif isinstance(ocr, dict):
            return OCRConfig(**ocr)
        return OCRConfig()
    
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
                    "litellm is required for OCR. "
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
        return params
    
    def _build_document(self, source: str) -> Dict[str, str]:
        """Build document dict from source URL or path."""
        # Determine if it's an image or document
        source_lower = source.lower()
        if any(ext in source_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            return {"type": "image_url", "image_url": source}
        else:
            return {"type": "document_url", "document_url": source}
    
    def extract(
        self,
        source: str,
        include_image_base64: Optional[bool] = None,
        pages: Optional[List[int]] = None,
        image_limit: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Extract text from a document or image.
        
        Args:
            source: URL or path to document/image
            include_image_base64: Include base64 images in response
            pages: Specific pages to extract (for PDFs)
            image_limit: Maximum images per page
            model: Override model for this call
            **kwargs: Additional parameters
            
        Returns:
            OCRResponse with pages, markdown content, and metadata
            
        Example:
            ```python
            agent = OCRAgent(llm="mistral/mistral-ocr-latest")
            result = agent.extract("https://arxiv.org/pdf/2201.04234")
            for page in result.pages:
                print(f"Page {page.index}: {page.markdown}")
            ```
        """
        model = model or self.llm
        
        params = self._get_model_params(model)
        params["document"] = self._build_document(source)
        
        # Apply config values
        if include_image_base64 is not None:
            params["include_image_base64"] = include_image_base64
        elif self._ocr_config.include_image_base64:
            params["include_image_base64"] = self._ocr_config.include_image_base64
            
        if pages is not None:
            params["pages"] = pages
        elif self._ocr_config.pages:
            params["pages"] = self._ocr_config.pages
            
        if image_limit is not None:
            params["image_limit"] = image_limit
        elif self._ocr_config.image_limit:
            params["image_limit"] = self._ocr_config.image_limit
        
        params.update(kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Extracting text with {model}...[/cyan]")
        
        response = self.litellm.ocr(**params)
        
        if self.verbose:
            self.console.print(f"[green]✓ OCR complete[/green]")
        
        return response
    
    async def aextract(
        self,
        source: str,
        include_image_base64: Optional[bool] = None,
        pages: Optional[List[int]] = None,
        image_limit: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Async version of extract()."""
        model = model or self.llm
        
        params = self._get_model_params(model)
        params["document"] = self._build_document(source)
        
        if include_image_base64 is not None:
            params["include_image_base64"] = include_image_base64
        elif self._ocr_config.include_image_base64:
            params["include_image_base64"] = self._ocr_config.include_image_base64
            
        if pages is not None:
            params["pages"] = pages
        elif self._ocr_config.pages:
            params["pages"] = self._ocr_config.pages
            
        if image_limit is not None:
            params["image_limit"] = image_limit
        elif self._ocr_config.image_limit:
            params["image_limit"] = self._ocr_config.image_limit
        
        params.update(kwargs)
        
        return await self.litellm.aocr(**params)
    
    # Convenience methods
    def read(self, source: str, **kwargs) -> str:
        """
        Quick OCR - extract and return markdown text.
        
        Args:
            source: URL or path to document/image
            
        Returns:
            Extracted text as markdown string
        """
        response = self.extract(source, **kwargs)
        
        # Combine all pages into markdown
        if hasattr(response, 'pages'):
            return "\n\n".join(
                page.markdown for page in response.pages 
                if hasattr(page, 'markdown')
            )
        return str(response)
    
    async def aread(self, source: str, **kwargs) -> str:
        """Async version of read()."""
        response = await self.aextract(source, **kwargs)
        
        if hasattr(response, 'pages'):
            return "\n\n".join(
                page.markdown for page in response.pages 
                if hasattr(page, 'markdown')
            )
        return str(response)
