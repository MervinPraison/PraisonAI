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
        
        # Get the model name robustly from the parent Agent's property
        model_info = self.llm_model
        model_name = model_info.model if hasattr(model_info, 'model') else str(model_info)
        
        # Use the model name in config
        config['model'] = model_name
        # Filter parameters based on the provider to avoid unsupported parameter errors
        custom_llm_provider = None
        try:
            import litellm
            _, custom_llm_provider, _, _ = litellm.get_llm_provider(model=model_name)
        except (ImportError, AttributeError, ValueError, TypeError, Exception) as e:
            # Log the specific error for debugging but continue with string-based fallback
            # Include generic Exception to catch provider-specific errors like BadRequestError
            logging.debug(f"Provider detection failed for model '{model_name}': {e}")
        
        if custom_llm_provider == "vertex_ai":
            # Vertex AI only supports 'n' and 'size' parameters for image generation
            supported_params = ['n', 'size', 'model']
            config = {k: v for k, v in config.items() if k in supported_params}
        elif custom_llm_provider == "gemini" or (custom_llm_provider is None and 'gemini' in model_name.lower()):
            # Gemini provider doesn't support response_format parameter
            # Apply this filter if provider is explicitly 'gemini' or as fallback for gemini models
            config.pop('response_format', None)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            try:
                # Add a task for image generation
                task = progress.add_task(f"[cyan]Generating image with {model_name}...", total=None)
                
                # Use litellm's image generation with parameter dropping enabled as safety net
                response = self.litellm(
                    prompt=prompt,
                    drop_params=True,
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
    
    # Aliases for consistency with other agents
    def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Alias for generate_image() - for consistency with VideoAgent/AudioAgent."""
        return self.generate_image(prompt, **kwargs)
    
    async def agenerate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Async alias for generate_image()."""
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

    def edit(
        self,
        image: str,
        prompt: str,
        mask: Optional[str] = None,
        n: int = 1,
        size: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Edit an existing image with a prompt.
        
        Args:
            image: Path or URL to the image to edit
            prompt: Description of the desired edits
            mask: Optional mask image (transparent areas will be edited)
            n: Number of images to generate
            size: Output image size
            **kwargs: Additional provider-specific parameters
            
        Returns:
            ImageResponse with edited image(s)
            
        Example:
            ```python
            agent = ImageAgent(llm="openai/dall-e-2")
            result = agent.edit("photo.png", "Add a sunset in the background")
            ```
        """
        try:
            import litellm
            litellm.telemetry = False
            
            model_name = self.llm or self.model or "dall-e-2"
            
            config = {
                "model": model_name,
                "image": image,
                "prompt": prompt,
                "n": n,
            }
            if mask:
                config["mask"] = mask
            if size:
                config["size"] = size
            if self.image_config.api_key:
                config["api_key"] = self.image_config.api_key
            if self.image_config.api_base:
                config["api_base"] = self.image_config.api_base
            
            config.update(kwargs)
            
            if self.verbose:
                self.console.print(f"[cyan]Editing image with {model_name}...[/cyan]")
            
            response = litellm.image_edit(**config)
            
            if self.verbose:
                self.console.print(f"[green]✓ Image edited successfully[/green]")
            
            return response
        except Exception as e:
            error_msg = f"Error editing image: {str(e)}"
            if self.verbose:
                self.console.print(f"[red]{error_msg}[/red]")
            raise

    async def aedit(
        self,
        image: str,
        prompt: str,
        mask: Optional[str] = None,
        n: int = 1,
        size: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Async version of edit()."""
        return self.edit(image, prompt, mask, n, size, **kwargs)

    def variation(
        self,
        image: str,
        n: int = 1,
        size: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate variations of an existing image.
        
        Args:
            image: Path or URL to the source image
            n: Number of variations to generate
            size: Output image size
            **kwargs: Additional provider-specific parameters
            
        Returns:
            ImageResponse with image variations
            
        Example:
            ```python
            agent = ImageAgent(llm="openai/dall-e-2")
            result = agent.variation("original.png", n=3)
            ```
        """
        try:
            import litellm
            litellm.telemetry = False
            
            model_name = self.llm or self.model or "dall-e-2"
            
            config = {
                "model": model_name,
                "image": image,
                "n": n,
            }
            if size:
                config["size"] = size
            if self.image_config.api_key:
                config["api_key"] = self.image_config.api_key
            if self.image_config.api_base:
                config["api_base"] = self.image_config.api_base
            
            config.update(kwargs)
            
            if self.verbose:
                self.console.print(f"[cyan]Generating variations with {model_name}...[/cyan]")
            
            response = litellm.image_variation(**config)
            
            if self.verbose:
                self.console.print(f"[green]✓ Variations generated successfully[/green]")
            
            return response
        except Exception as e:
            error_msg = f"Error generating variations: {str(e)}"
            if self.verbose:
                self.console.print(f"[red]{error_msg}[/red]")
            raise

    async def avariation(
        self,
        image: str,
        n: int = 1,
        size: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Async version of variation()."""
        return self.variation(image, n, size, **kwargs)

