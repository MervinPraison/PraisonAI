"""
VisionAgent - A specialized agent for image analysis and understanding.

This agent provides vision capabilities for analyzing, describing, and
extracting information from images using AI vision models.

Follows the Agent() class patterns with:
- Lazy loading for heavy dependencies (litellm, rich)
- Precedence Ladder for configuration resolution
- Both sync and async methods
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, List
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VisionConfig:
    """
    Configuration for vision processing settings.
    
    Follows the Precedence Ladder pattern:
    - Instance > Config > Array > Dict > String > Bool > Default
    """
    detail: str = "auto"  # low, high, auto
    max_tokens: int = 4096
    timeout: int = 60
    
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LiteLLM calls."""
        return {
            "detail": self.detail,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "api_base": self.api_base,
            "api_key": self.api_key,
        }


class VisionAgent:
    """
    A specialized agent for image analysis and understanding.
    
    Provides:
    - Image analysis and description
    - Multi-image comparison
    - Text extraction from images
    
    Supported Providers:
        - OpenAI: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`
        - Anthropic: `claude-3-5-sonnet-20241022`, `claude-3-opus-20240229`
        - Google: `gemini/gemini-1.5-pro`, `gemini/gemini-1.5-flash`
    
    Example:
        ```python
        from praisonaiagents import VisionAgent
        
        # Simple usage
        agent = VisionAgent()
        description = agent.describe("https://example.com/image.jpg")
        print(description)
        
        # Analyze with custom prompt
        result = agent.analyze(
            "https://example.com/chart.png",
            prompt="What data does this chart show?"
        )
        
        # Compare images
        comparison = agent.compare([
            "image1.jpg",
            "image2.jpg"
        ])
        
        # Extract text
        text = agent.extract_text("document.png")
        ```
    """
    
    DEFAULT_MODEL = "gpt-4o"
    
    def __init__(
        self,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        vision: Optional[Union[bool, Dict, "VisionConfig"]] = None,
        verbose: Union[bool, int] = True,
    ):
        """Initialize VisionAgent.
        
        Args:
            name: Agent name for identification
            instructions: Optional instructions for the agent
            llm: Model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            model: Alias for llm= parameter
            base_url: Custom API endpoint URL
            api_key: API key for the provider
            vision: Vision configuration. Accepts:
                - bool: True enables with defaults
                - dict: {"detail": "high", "max_tokens": 8192}
                - VisionConfig: Full configuration object
            verbose: Verbosity level for output
        """
        if llm is None and model is not None:
            llm = model
        
        self.name = name or "VisionAgent"
        self.instructions = instructions
        self.llm = llm or os.getenv('PRAISONAI_VISION_MODEL', self.DEFAULT_MODEL)
        self.base_url = base_url
        self.api_key = api_key
        self._vision_config = self._resolve_vision_config(vision)
        self.verbose = verbose
        
        self._litellm = None
        self._console = None
        
        self._configure_logging(verbose)
    
    def _resolve_vision_config(self, vision: Optional[Union[bool, Dict, VisionConfig]]) -> VisionConfig:
        """Resolve vision parameter using Precedence Ladder."""
        if vision is None or vision is True or vision is False:
            return VisionConfig()
        elif isinstance(vision, VisionConfig):
            return vision
        elif isinstance(vision, dict):
            return VisionConfig(**vision)
        return VisionConfig()
    
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
                    "litellm is required for vision processing. "
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
    
    def _build_image_content(self, image: str, detail: Optional[str] = None) -> Dict[str, Any]:
        """Build image content for vision API."""
        detail = detail or self._vision_config.detail
        
        if image.startswith(('http://', 'https://')):
            return {
                "type": "image_url",
                "image_url": {"url": image, "detail": detail}
            }
        else:
            import base64
            path = Path(image)
            if path.exists():
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                ext = path.suffix.lower().lstrip('.')
                mime = f"image/{ext}" if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp') else "image/png"
                return {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{data}", "detail": detail}
                }
            else:
                return {
                    "type": "image_url",
                    "image_url": {"url": image, "detail": detail}
                }
    
    def analyze(
        self,
        image: str,
        prompt: Optional[str] = None,
        detail: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Analyze an image and return analysis.
        
        Args:
            image: Image URL or local file path
            prompt: Custom prompt for analysis (default: general analysis)
            detail: Detail level (low, high, auto)
            model: Override model for this call
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Analysis text
            
        Example:
            ```python
            agent = VisionAgent()
            result = agent.analyze(
                "https://example.com/chart.png",
                prompt="What trends does this chart show?"
            )
            ```
        """
        prompt = prompt or "Analyze this image in detail. Describe what you see, including objects, colors, composition, and any text or data present."
        
        params = self._get_model_params(model)
        params["messages"] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    self._build_image_content(image, detail)
                ]
            }
        ]
        params["max_tokens"] = kwargs.pop("max_tokens", self._vision_config.max_tokens)
        params.update(kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Analyzing image with {params['model']}...[/cyan]")
        
        response = self.litellm.completion(**params)
        result = response.choices[0].message.content
        
        if self.verbose:
            self.console.print("[green]✓ Analysis complete[/green]")
        
        return result
    
    def describe(
        self,
        image: str,
        detail: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate a detailed description of an image.
        
        Args:
            image: Image URL or local file path
            detail: Detail level (low, high, auto)
            model: Override model for this call
            **kwargs: Additional parameters
            
        Returns:
            Detailed description text
            
        Example:
            ```python
            agent = VisionAgent()
            description = agent.describe("photo.jpg")
            print(description)
            ```
        """
        prompt = """Provide a comprehensive description of this image. Include:
1. Main subject and composition
2. Colors, lighting, and mood
3. Background and setting
4. Any text, symbols, or notable details
5. Overall impression and context"""
        
        return self.analyze(image, prompt=prompt, detail=detail, model=model, **kwargs)
    
    def compare(
        self,
        images: List[str],
        prompt: Optional[str] = None,
        detail: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Compare multiple images.
        
        Args:
            images: List of image URLs or file paths
            prompt: Custom comparison prompt
            detail: Detail level (low, high, auto)
            model: Override model for this call
            **kwargs: Additional parameters
            
        Returns:
            Comparison analysis text
            
        Example:
            ```python
            agent = VisionAgent()
            comparison = agent.compare([
                "before.jpg",
                "after.jpg"
            ], prompt="What changed between these images?")
            ```
        """
        if len(images) < 2:
            raise ValueError("At least 2 images are required for comparison")
        
        prompt = prompt or f"Compare these {len(images)} images. Describe their similarities and differences in detail."
        
        content = [{"type": "text", "text": prompt}]
        for i, img in enumerate(images):
            content.append(self._build_image_content(img, detail))
        
        params = self._get_model_params(model)
        params["messages"] = [{"role": "user", "content": content}]
        params["max_tokens"] = kwargs.pop("max_tokens", self._vision_config.max_tokens)
        params.update(kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Comparing {len(images)} images with {params['model']}...[/cyan]")
        
        response = self.litellm.completion(**params)
        result = response.choices[0].message.content
        
        if self.verbose:
            self.console.print("[green]✓ Comparison complete[/green]")
        
        return result
    
    def extract_text(
        self,
        image: str,
        detail: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Extract text from an image (OCR-like functionality).
        
        Args:
            image: Image URL or local file path
            detail: Detail level (low, high, auto) - recommend "high" for text
            model: Override model for this call
            **kwargs: Additional parameters
            
        Returns:
            Extracted text
            
        Example:
            ```python
            agent = VisionAgent()
            text = agent.extract_text("document.png", detail="high")
            print(text)
            ```
        """
        detail = detail or "high"
        prompt = """Extract ALL text visible in this image. 
Preserve the original formatting and structure as much as possible.
Include headers, paragraphs, lists, tables, captions, and any other text.
If text is unclear, indicate with [unclear].
Return ONLY the extracted text, no additional commentary."""
        
        return self.analyze(image, prompt=prompt, detail=detail, model=model, **kwargs)
    
    async def aanalyze(
        self,
        image: str,
        prompt: Optional[str] = None,
        detail: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Async version of analyze()."""
        prompt = prompt or "Analyze this image in detail."
        
        params = self._get_model_params(model)
        params["messages"] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    self._build_image_content(image, detail)
                ]
            }
        ]
        params["max_tokens"] = kwargs.pop("max_tokens", self._vision_config.max_tokens)
        params.update(kwargs)
        
        response = await self.litellm.acompletion(**params)
        return response.choices[0].message.content
    
    async def adescribe(self, image: str, **kwargs) -> str:
        """Async version of describe()."""
        prompt = "Provide a comprehensive description of this image."
        return await self.aanalyze(image, prompt=prompt, **kwargs)
    
    async def acompare(self, images: List[str], **kwargs) -> str:
        """Async version of compare()."""
        if len(images) < 2:
            raise ValueError("At least 2 images are required for comparison")
        
        prompt = kwargs.pop("prompt", None) or f"Compare these {len(images)} images."
        detail = kwargs.pop("detail", None)
        model = kwargs.pop("model", None)
        
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append(self._build_image_content(img, detail))
        
        params = self._get_model_params(model)
        params["messages"] = [{"role": "user", "content": content}]
        params["max_tokens"] = kwargs.pop("max_tokens", self._vision_config.max_tokens)
        params.update(kwargs)
        
        response = await self.litellm.acompletion(**params)
        return response.choices[0].message.content
    
    async def aextract_text(self, image: str, **kwargs) -> str:
        """Async version of extract_text()."""
        kwargs.setdefault("detail", "high")
        prompt = "Extract ALL text visible in this image. Preserve formatting."
        return await self.aanalyze(image, prompt=prompt, **kwargs)
