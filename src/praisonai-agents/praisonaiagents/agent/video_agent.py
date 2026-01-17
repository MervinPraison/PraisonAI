"""
VideoAgent - A specialized agent class for generating videos using AI models.
This class extends the base Agent class to provide specific functionality for video generation,
including support for different video models, sizes, durations, and polling workflow.

Follows the Agent() class patterns:
- Precedence Ladder: Instance > Config > Array > Dict > String > Bool > Default
- Lazy imports for LiteLLM (zero overhead until first use)
- Async-safe with both sync and async methods
- Multi-agent safe (no shared state)
"""
import os
import time
import logging
import asyncio
import warnings
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, Union, List, Generator
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# Filter out Pydantic warning about fields
warnings.filterwarnings("ignore", "Valid config keys have changed in V2", UserWarning)


# ─────────────────────────────────────────────────────────────────────────────
# VideoConfig - Configuration dataclass following feature_configs.py patterns
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VideoConfig:
    """
    Configuration for video generation settings.
    
    Follows the Precedence Ladder pattern:
    - Instance > Config > Array > Dict > String > Bool > Default
    
    Usage:
        # Simple string (model name)
        VideoAgent(llm="openai/sora-2")
        
        # Bool (enable/disable - uses default model)
        VideoAgent(video=True)  # Uses default model
        
        # Dict
        VideoAgent(video={"seconds": "8", "size": "1280x720"})
        
        # Config instance
        VideoAgent(video=VideoConfig(seconds="16", size="720x1280"))
    """
    # Video duration in seconds
    seconds: Optional[str] = "8"
    
    # Video dimensions (e.g., "720x1280", "1280x720")
    size: Optional[str] = None
    
    # Reference image for image-to-video or remix operations
    input_reference: Optional[Any] = None
    
    # Timeout for generation request (video generation can take minutes)
    timeout: int = 600
    
    # Optional API configuration (usually inherited from llm= param)
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    api_version: Optional[str] = None
    
    # Polling configuration for wait_for_completion
    poll_interval: int = 10  # seconds between status checks
    max_wait_time: int = 600  # maximum wait time in seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LiteLLM calls."""
        return {
            "seconds": self.seconds,
            "size": self.size,
            "input_reference": self.input_reference,
            "timeout": self.timeout,
            "api_base": self.api_base,
            "api_key": self.api_key,
            "api_version": self.api_version,
        }


# ─────────────────────────────────────────────────────────────────────────────
# VideoAgent Class - Agent-centric video generation
# ─────────────────────────────────────────────────────────────────────────────

class VideoAgent:
    """
    A specialized agent for generating videos using AI models.
    
    This agent provides a simple, agent-centric interface for video generation
    with support for multiple providers (OpenAI Sora, Azure, Gemini Veo, Vertex AI, RunwayML).
    
    Supported Providers:
        - OpenAI: openai/sora-2, openai/sora-2-pro
        - Azure: azure/sora-2, azure/sora-2-pro
        - Gemini: gemini/veo-3.0-generate-preview, gemini/veo-3.1-*
        - Vertex AI: vertex_ai/veo-3.0-*, vertex_ai/veo-3.1-*
        - RunwayML: runwayml/gen4_turbo (requires input_reference)
    
    Example:
        ```python
        from praisonaiagents import VideoAgent
        
        # Simple usage
        agent = VideoAgent(llm="openai/sora-2")
        video = agent.generate(prompt="A cat playing with yarn")
        
        # Wait for completion
        video = agent.start(
            prompt="A serene lake at sunset",
            wait=True,  # Wait for completion
            output="video.mp4"  # Save to file
        )
        
        # With config
        agent = VideoAgent(
            llm="gemini/veo-3.0-generate-preview",
            video=VideoConfig(seconds="8", size="1280x720")
        )
        ```
    """
    
    # Default model when none specified
    DEFAULT_MODEL = "openai/sora-2"
    
    def __init__(
        self,
        # Core identity (optional for VideoAgent)
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        # LLM configuration - primary way to specify model
        llm: Optional[Union[str, Any]] = None,
        model: Optional[Union[str, Any]] = None,  # Alias for llm=
        # Connection/auth (kept separate per Agent pattern)
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        # Video-specific configuration
        video: Optional[Union[bool, Dict, "VideoConfig"]] = None,
        # Output configuration
        verbose: Union[bool, int] = True,
        output: Optional[str] = None,  # Output preset
    ):
        """Initialize VideoAgent.
        
        Args:
            name: Agent name for identification
            instructions: Optional instructions (unused for video generation)
            llm: Model name string (e.g., "openai/sora-2", "gemini/veo-3.0-generate-preview")
            model: Alias for llm= parameter
            base_url: Custom API endpoint URL
            api_key: API key for the provider
            api_version: API version (for Azure)
            video: Video generation configuration. Accepts:
                - bool: True enables with defaults
                - dict: {"seconds": "8", "size": "1280x720"}
                - VideoConfig: Full configuration object
            verbose: Verbosity level for output
            output: Output preset ("silent", "verbose", etc.)
        """
        # Handle model= alias for llm=
        if llm is None and model is not None:
            llm = model
        
        # Store core identity
        self.name = name or "VideoAgent"
        self.instructions = instructions
        
        # Store the model name
        self.llm = llm or os.getenv('PRAISONAI_VIDEO_MODEL', self.DEFAULT_MODEL)
        
        # Store connection parameters (kept separate per Agent pattern)
        self.base_url = base_url
        self.api_key = api_key
        self.api_version = api_version
        
        # Resolve video configuration using Precedence Ladder
        self._video_config = self._resolve_video_config(video)
        
        # Output configuration
        self.verbose = verbose
        self._output_preset = output
        
        # Lazy load LiteLLM video module (zero overhead until first use)
        self._litellm_video = None
        self._litellm = None
        
        # Console for Rich output
        self._console = None
        
        # Configure logging
        self._configure_logging(verbose)
    
    def _resolve_video_config(self, video: Optional[Union[bool, Dict, VideoConfig]]) -> VideoConfig:
        """
        Resolve video parameter using Precedence Ladder.
        
        Precedence: Instance > Config > Array > Dict > String > Bool > Default
        """
        if video is None or video is True:
            return VideoConfig()
        elif video is False:
            return VideoConfig()
        elif isinstance(video, VideoConfig):
            return video
        elif isinstance(video, dict):
            return VideoConfig(**video)
        else:
            return VideoConfig()
    
    @property
    def console(self) -> Console:
        """Lazily initialize Rich Console."""
        if self._console is None:
            self._console = Console()
        return self._console
    
    @property
    def video_module(self):
        """Lazy load litellm.videos module when needed."""
        if self._litellm_video is None:
            try:
                from litellm.videos import (
                    video_generation,
                    avideo_generation,
                    video_status,
                    avideo_status,
                    video_content,
                    avideo_content,
                    video_list,
                    avideo_list,
                    video_remix,
                    avideo_remix,
                )
                import litellm
                
                # Disable LiteLLM telemetry and debug logging
                litellm.telemetry = False
                litellm.success_callback = []
                
                self._litellm_video = {
                    "video_generation": video_generation,
                    "avideo_generation": avideo_generation,
                    "video_status": video_status,
                    "avideo_status": avideo_status,
                    "video_content": video_content,
                    "avideo_content": avideo_content,
                    "video_list": video_list,
                    "avideo_list": avideo_list,
                    "video_remix": video_remix,
                    "avideo_remix": avideo_remix,
                }
                self._litellm = litellm
                
            except ImportError:
                raise ImportError(
                    "litellm is required for video generation. "
                    "Please install with: pip install litellm"
                )
        return self._litellm_video
    
    def _configure_logging(self, verbose: Union[bool, int]) -> None:
        """Configure logging levels based on verbose setting."""
        if isinstance(verbose, int) and verbose >= 10:
            # Debug mode
            logging.getLogger("litellm").setLevel(logging.DEBUG)
        else:
            # Suppress debug logging
            logging.getLogger("litellm").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    def _get_model_params(self) -> Dict[str, Any]:
        """Build parameters for LiteLLM video calls."""
        params = {"model": self.llm}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["api_base"] = self.base_url
        if self.api_version:
            params["api_version"] = self.api_version
        return params
    
    # ─────────────────────────────────────────────────────────────────────────
    # Core Video Operations (5 operations, sync + async)
    # ─────────────────────────────────────────────────────────────────────────
    
    def generate(
        self,
        prompt: str,
        seconds: Optional[str] = None,
        size: Optional[str] = None,
        input_reference: Optional[Any] = None,
        **kwargs
    ) -> Any:
        """
        Generate a video from a text prompt.
        
        Args:
            prompt: Text description of the desired video
            seconds: Video duration (e.g., "8", "16"). Defaults to config value.
            size: Video dimensions (e.g., "720x1280"). Defaults to config value.
            input_reference: Reference image for image-to-video generation
            **kwargs: Additional provider-specific parameters
            
        Returns:
            VideoObject with id, status, and metadata
            
        Example:
            ```python
            video = agent.generate(
                prompt="A cat playing with yarn",
                seconds="8",
                size="1280x720"
            )
            print(f"Video ID: {video.id}")
            print(f"Status: {video.status}")
            ```
        """
        # Merge config with kwargs
        config = self._video_config.to_dict()
        if seconds:
            config["seconds"] = seconds
        if size:
            config["size"] = size
        if input_reference:
            config["input_reference"] = input_reference
        config.update(kwargs)
        
        # Remove None values
        config = {k: v for k, v in config.items() if v is not None}
        
        # Get model parameters
        params = self._get_model_params()
        params["prompt"] = prompt
        params.update(config)
        
        # Remove internal config keys
        params.pop("poll_interval", None)
        params.pop("max_wait_time", None)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            try:
                task = progress.add_task(f"[cyan]Generating video with {self.llm}...", total=None)
                response = self.video_module["video_generation"](**params)
                progress.update(task, completed=True)
                return response
            except Exception as e:
                if self.verbose:
                    self.console.print(f"[red]Error generating video: {e}[/red]")
                raise
    
    async def agenerate(
        self,
        prompt: str,
        seconds: Optional[str] = None,
        size: Optional[str] = None,
        input_reference: Optional[Any] = None,
        **kwargs
    ) -> Any:
        """Async version of generate()."""
        config = self._video_config.to_dict()
        if seconds:
            config["seconds"] = seconds
        if size:
            config["size"] = size
        if input_reference:
            config["input_reference"] = input_reference
        config.update(kwargs)
        config = {k: v for k, v in config.items() if v is not None}
        
        params = self._get_model_params()
        params["prompt"] = prompt
        params.update(config)
        params.pop("poll_interval", None)
        params.pop("max_wait_time", None)
        
        return await self.video_module["avideo_generation"](**params)
    
    def status(self, video_id: str, **kwargs) -> Any:
        """
        Check the status of a video generation.
        
        Args:
            video_id: The video ID returned from generate()
            **kwargs: Additional parameters
            
        Returns:
            VideoObject with updated status
        """
        return self.video_module["video_status"](video_id=video_id, **kwargs)
    
    async def astatus(self, video_id: str, **kwargs) -> Any:
        """Async version of status()."""
        return await self.video_module["avideo_status"](video_id=video_id, **kwargs)
    
    def content(self, video_id: str, **kwargs) -> bytes:
        """
        Download the video content.
        
        Args:
            video_id: The video ID to download
            **kwargs: Additional parameters
            
        Returns:
            Raw video bytes (MP4 format)
        """
        return self.video_module["video_content"](video_id=video_id, **kwargs)
    
    async def acontent(self, video_id: str, **kwargs) -> bytes:
        """Async version of content()."""
        return await self.video_module["avideo_content"](video_id=video_id, **kwargs)
    
    def list(self, **kwargs) -> List[Any]:
        """
        List all videos for the current account.
        
        Note: Requires custom_llm_provider for some providers.
        
        Args:
            **kwargs: Additional parameters (e.g., custom_llm_provider="openai")
            
        Returns:
            List of VideoObject
        """
        return self.video_module["video_list"](**kwargs)
    
    async def alist(self, **kwargs) -> List[Any]:
        """Async version of list()."""
        return await self.video_module["avideo_list"](**kwargs)
    
    def remix(self, video_id: str, prompt: str, **kwargs) -> Any:
        """
        Remix/edit an existing video.
        
        Args:
            video_id: The ID of the completed video to remix
            prompt: New prompt describing the desired changes
            **kwargs: Additional parameters
            
        Returns:
            New VideoObject for the remixed video
        """
        return self.video_module["video_remix"](
            video_id=video_id,
            prompt=prompt,
            **kwargs
        )
    
    async def aremix(self, video_id: str, prompt: str, **kwargs) -> Any:
        """Async version of remix()."""
        return await self.video_module["avideo_remix"](
            video_id=video_id,
            prompt=prompt,
            **kwargs
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Convenience Methods (following Agent.start()/run() patterns)
    # ─────────────────────────────────────────────────────────────────────────
    
    def wait_for_completion(
        self,
        video_id: str,
        poll_interval: Optional[int] = None,
        max_wait_time: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Wait for video generation to complete.
        
        Args:
            video_id: The video ID to poll
            poll_interval: Seconds between status checks (default: 10)
            max_wait_time: Maximum wait time in seconds (default: 600)
            
        Returns:
            VideoObject with status "completed" or "failed"
            
        Raises:
            TimeoutError: If max_wait_time is exceeded
        """
        poll_interval = poll_interval or self._video_config.poll_interval
        max_wait_time = max_wait_time or self._video_config.max_wait_time
        
        start_time = time.time()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Waiting for video...", total=None)
            
            while time.time() - start_time < max_wait_time:
                status_response = self.status(video_id, **kwargs)
                
                if status_response.status == "completed":
                    progress.update(task, completed=True)
                    if self.verbose:
                        self.console.print("[green]✓ Video generation completed![/green]")
                    return status_response
                elif status_response.status == "failed":
                    progress.update(task, completed=True)
                    if self.verbose:
                        self.console.print("[red]✗ Video generation failed[/red]")
                    return status_response
                
                progress.update(task, description=f"[cyan]Status: {status_response.status}...")
                time.sleep(poll_interval)
            
            raise TimeoutError(
                f"Video generation did not complete within {max_wait_time} seconds"
            )
    
    async def await_completion(
        self,
        video_id: str,
        poll_interval: Optional[int] = None,
        max_wait_time: Optional[int] = None,
        **kwargs
    ) -> Any:
        """Async version of wait_for_completion()."""
        poll_interval = poll_interval or self._video_config.poll_interval
        max_wait_time = max_wait_time or self._video_config.max_wait_time
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            status_response = await self.astatus(video_id, **kwargs)
            
            if status_response.status == "completed":
                return status_response
            elif status_response.status == "failed":
                return status_response
            
            await asyncio.sleep(poll_interval)
        
        raise TimeoutError(
            f"Video generation did not complete within {max_wait_time} seconds"
        )
    
    def start(
        self,
        prompt: str,
        wait: bool = True,
        output: Optional[str] = None,
        **kwargs
    ) -> Union[Any, bytes]:
        """
        Generate video with optional wait and file output.
        
        Beginner-friendly method that handles the full workflow:
        1. Generate video
        2. Wait for completion (if wait=True)
        3. Download and save to file (if output is specified)
        
        Args:
            prompt: Text description of the desired video
            wait: If True, wait for completion before returning
            output: Path to save the video file (e.g., "video.mp4")
            **kwargs: Additional parameters for generate()
            
        Returns:
            - If wait=False: VideoObject with initial status
            - If wait=True and output: bytes (video content)
            - If wait=True and no output: VideoObject with completed status
            
        Example:
            ```python
            # Full workflow with file output
            video = agent.start(
                prompt="A serene lake at sunset",
                wait=True,
                output="sunset.mp4"
            )
            
            # Just generate (don't wait)
            video = agent.start(
                prompt="A cat playing",
                wait=False
            )
            print(f"Video ID: {video.id}")  # Poll later with status()
            ```
        """
        # Step 1: Generate
        video = self.generate(prompt, **kwargs)
        
        if self.verbose:
            self.console.print(f"[cyan]Video ID: {video.id}[/cyan]")
            self.console.print(f"[cyan]Initial Status: {video.status}[/cyan]")
        
        if not wait:
            return video
        
        # Step 2: Wait for completion
        completed_video = self.wait_for_completion(video.id)
        
        if completed_video.status != "completed":
            return completed_video
        
        # Step 3: Download and optionally save
        if output:
            video_bytes = self.content(video.id)
            with open(output, "wb") as f:
                f.write(video_bytes)
            if self.verbose:
                self.console.print(f"[green]✓ Video saved to {output}[/green]")
            return video_bytes
        
        return completed_video
    
    async def astart(
        self,
        prompt: str,
        wait: bool = True,
        output: Optional[str] = None,
        **kwargs
    ) -> Union[Any, bytes]:
        """Async version of start()."""
        video = await self.agenerate(prompt, **kwargs)
        
        if not wait:
            return video
        
        completed_video = await self.await_completion(video.id)
        
        if completed_video.status != "completed":
            return completed_video
        
        if output:
            video_bytes = await self.acontent(video.id)
            with open(output, "wb") as f:
                f.write(video_bytes)
            return video_bytes
        
        return completed_video
    
    def run(self, prompt: str, **kwargs) -> Any:
        """
        Generate video silently (production use).
        
        Unlike start(), this method is always silent regardless of verbose setting.
        Use for programmatic/scripted usage.
        
        Args:
            prompt: Text description of the desired video
            **kwargs: Additional parameters
            
        Returns:
            VideoObject (does not wait for completion)
        """
        return self.generate(prompt, **kwargs)
    
    async def arun(self, prompt: str, **kwargs) -> Any:
        """Async version of run()."""
        return await self.agenerate(prompt, **kwargs)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def download(self, video_id: str, output: str) -> str:
        """
        Download a video to a file.
        
        Args:
            video_id: The video ID to download
            output: Path to save the video file
            
        Returns:
            Path to the saved file
        """
        video_bytes = self.content(video_id)
        with open(output, "wb") as f:
            f.write(video_bytes)
        if self.verbose:
            self.console.print(f"[green]✓ Video saved to {output}[/green]")
        return output
    
    async def adownload(self, video_id: str, output: str) -> str:
        """Async version of download()."""
        video_bytes = await self.acontent(video_id)
        with open(output, "wb") as f:
            f.write(video_bytes)
        return output
