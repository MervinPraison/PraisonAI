"""
ImageAgent - A specialized agent class for generating images using AI models.

This class extends the base Agent class to provide specific functionality for image generation,
including support for different image models, sizes, and quality settings.
"""

from typing import Optional, Any, Dict, Union, List
from ..agent.agent import Agent
from pydantic import BaseModel, Field
import logging
import warnings

# Filter out Pydantic warning about fields
warnings.filterwarnings("ignore", "Valid config keys have changed in V2", UserWarning)

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

class ImageGenerationConfig(BaseModel):
    """Configuration for image generation settings."""
    style: str = Field(default="natural", description="Style of the generated image")
    response_format: str = Field(default="url", description="Format of the response (url or b64_json)")
    timeout: int = Field(default=600, description="Timeout in seconds for the API call")
    api_base: Optional[str] = Field(default=None, description="Optional API base URL")
    api_key: Optional[str] = Field(default=None, description="Optional API key")
    api_version: Optional[str] = Field(default=None, description="Optional API version (required for Azure dall-e-3)")

class ImageAgent(Agent):
    """
    A specialized agent for generating images using AI models.
    
    This agent extends the base Agent class with specific functionality for image generation,
    including support for different models, sizes, and quality settings.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[Union[str, Any]] = None,
        style: str = "natural",
        response_format: str = "url",
        timeout: int = 600,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        verbose: Union[bool, int] = True,
        **kwargs
    ):
        """Initialize ImageAgent with parameters."""
        # Set default role and goal if not provided
        role = role or "Image Generation Assistant"
        goal = goal or "Generate high-quality images based on text descriptions"
        backstory = backstory or "I am an AI assistant specialized in generating images from textual descriptions"

        # Initialize the base agent
        super().__init__(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            llm=llm,
            verbose=verbose,
            **kwargs
        )

        # Store image generation configuration
        self.image_config = ImageGenerationConfig(
            style=style,
            response_format=response_format,
            timeout=timeout,
            api_base=api_base,
            api_key=api_key,
            api_version=api_version
        )
        
        # Lazy load litellm
        self._litellm = None

        # Configure logging based on verbose level
        self._configure_logging(verbose)

    def _configure_logging(self, verbose: Union[bool, int]) -> None:
        """Configure logging levels based on verbose setting."""
        # Only suppress logs if not in debug mode
        if not isinstance(verbose, bool) and verbose >= 10:
            # Enable detailed debug logging
            logging.getLogger("asyncio").setLevel(logging.DEBUG)
            logging.getLogger("selector_events").setLevel(logging.DEBUG)
            logging.getLogger("litellm.utils").setLevel(logging.DEBUG)
            logging.getLogger("litellm.main").setLevel(logging.DEBUG)
            if hasattr(self, 'litellm'):
                self.litellm.suppress_debug_messages = False
                self.litellm.set_verbose = True
            # Don't filter warnings in debug mode
            warnings.resetwarnings()
        else:
            # Suppress debug logging for normal operation
            logging.getLogger("asyncio").setLevel(logging.WARNING)
            logging.getLogger("selector_events").setLevel(logging.WARNING)
            logging.getLogger("litellm.utils").setLevel(logging.WARNING)
            logging.getLogger("litellm.main").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("httpcore").setLevel(logging.WARNING)
            if hasattr(self, 'litellm'):
                self.litellm.suppress_debug_messages = True
                self.litellm._logging._disable_debugging()
            # Suppress all warnings including Pydantic's
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            warnings.filterwarnings("ignore", category=UserWarning)
            warnings.filterwarnings("ignore", category=DeprecationWarning)

    @property
    def litellm(self):
        """Lazy load litellm module when needed."""
        if self._litellm is None:
            try:
                import litellm
                from litellm import image_generation
                
                # Configure litellm to disable success handler logs
                litellm.success_callback = []
                litellm._logging._disable_debugging()
                
                self._litellm = image_generation
                # Configure logging after litellm is loaded
                self._configure_logging(self.verbose)
            except ImportError:
                raise ImportError(
                    "litellm is required for image generation. "
                    "Please install it with: pip install litellm"
                )
        return self._litellm

    def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate an image based on the provided prompt."""
        # Merge default config with any provided kwargs
        config = self.image_config.dict(exclude_none=True)
        config.update(kwargs)
        
        # Use llm parameter as the model
        config['model'] = self.llm

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            try:
                # Add a task for image generation
                task = progress.add_task(f"[cyan]Generating image with {self.llm}...", total=None)
                
                # Use litellm's image generation
                response = self.litellm(
                    prompt=prompt,
                    **config
                )
                
                # Mark task as complete
                progress.update(task, completed=True)
                return response

            except Exception as e:
                error_msg = f"Error generating image: {str(e)}"
                if self.verbose:
                    self.console.print(f"[red]{error_msg}[/red]")
                logging.error(error_msg)
                raise

    async def agenerate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Async wrapper for generate_image."""
        return self.generate_image(prompt, **kwargs)

    def chat(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate an image from the prompt."""
        try:
            result = self.generate_image(prompt, **kwargs)
            if self.verbose:
                self.console.print(f"[green]Successfully generated image from prompt[/green]")
            return result
        except Exception as e:
            error_msg = f"Failed to generate image: {str(e)}"
            if self.verbose:
                self.console.print(f"[red]{error_msg}[/red]")
            return {"error": str(e)}

    async def achat(
        self,
        prompt: str,
        temperature: float = 0.2,
        tools: Optional[List[Any]] = None,
        output_json: Optional[str] = None,
        output_pydantic: Optional[Any] = None,
        reasoning_steps: bool = False,
        **kwargs
    ) -> Union[str, Dict[str, Any]]:
        """Async chat method for image generation."""
        try:
            image_result = await self.agenerate_image(prompt, **kwargs)
            if self.verbose:
                self.console.print(f"[green]Successfully generated image from prompt[/green]")
            return image_result
        except Exception as e:
            error_msg = f"Failed to generate image: {str(e)}"
            if self.verbose:
                self.console.print(f"[red]{error_msg}[/red]")
            return {"error": str(e)}
