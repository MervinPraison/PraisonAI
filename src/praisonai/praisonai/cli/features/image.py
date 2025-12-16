"""
Image Handler for CLI.

Provides image processing capabilities using ImageAgent.
Usage: praisonai "Describe this image" --image path/to/image.png
"""

import os
from typing import Any, Dict, Tuple, List
from .base import FlagHandler

# Supported image extensions
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}


class ImageHandler(FlagHandler):
    """
    Handler for --image flag.
    
    Processes images using ImageAgent for vision-based tasks.
    
    Example:
        praisonai "Describe this image" --image photo.png
        praisonai "What's in this image?" --image /path/to/image.jpg
    """
    
    @property
    def feature_name(self) -> str:
        return "image"
    
    @property
    def flag_name(self) -> str:
        return "image"
    
    @property
    def flag_help(self) -> str:
        return "Path to image file for vision-based tasks"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if ImageAgent is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents") is not None:
                return True, ""
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
        except ImportError:
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
    
    def validate_image_path(self, path: str) -> Tuple[bool, str]:
        """
        Validate that the image path is valid.
        
        Args:
            path: Path to the image file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not path:
            return False, "No image path provided"
        
        # Check extension
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return False, f"Unsupported image format: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        
        # Check if file exists (for local files)
        if not path.startswith(('http://', 'https://')):
            if not os.path.exists(path):
                return False, f"Image file not found: {path}"
        
        return True, ""
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply image configuration to agent config.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Image path or list of paths
            
        Returns:
            Modified configuration with image settings
        """
        if flag_value:
            # Store image path(s) for use with ImageAgent
            if isinstance(flag_value, str):
                config["images"] = [flag_value]
            elif isinstance(flag_value, list):
                config["images"] = flag_value
            config["use_image_agent"] = True
        return config
    
    def create_image_agent(self, llm: str = None, **kwargs) -> Any:
        """
        Create an ImageAgent instance.
        
        Args:
            llm: Optional LLM model name
            **kwargs: Additional agent configuration
            
        Returns:
            ImageAgent instance or None if unavailable
        """
        available, msg = self.check_dependencies()
        if not available:
            self.print_status(msg, "error")
            return None
        
        from praisonaiagents import ImageAgent
        
        agent_config = {
            "name": "ImageAnalyzer",
            "role": "Image Analyst",
            "goal": "Analyze and describe images accurately",
            "backstory": "Expert at understanding visual content"
        }
        
        if llm:
            agent_config["llm"] = llm
        
        agent_config.update(kwargs)
        
        return ImageAgent(**agent_config)
    
    def process_image(self, prompt: str, image_path: str, llm: str = None) -> str:
        """
        Process an image with the given prompt.
        
        Args:
            prompt: The prompt/question about the image
            image_path: Path to the image file
            llm: Optional LLM model name
            
        Returns:
            Agent's response about the image
        """
        # Validate image path
        valid, msg = self.validate_image_path(image_path)
        if not valid:
            return f"Error: {msg}"
        
        agent = self.create_image_agent(llm=llm)
        if not agent:
            return "Error: Could not create ImageAgent"
        
        try:
            # ImageAgent expects images as a list
            result = agent.chat(prompt, images=[image_path])
            return result
        except Exception as e:
            self.log(f"Image processing error: {e}", "error")
            return f"Error processing image: {e}"
    
    def process_multiple_images(self, prompt: str, image_paths: List[str], llm: str = None) -> str:
        """
        Process multiple images with the given prompt.
        
        Args:
            prompt: The prompt/question about the images
            image_paths: List of paths to image files
            llm: Optional LLM model name
            
        Returns:
            Agent's response about the images
        """
        # Validate all image paths
        for path in image_paths:
            valid, msg = self.validate_image_path(path)
            if not valid:
                return f"Error: {msg}"
        
        agent = self.create_image_agent(llm=llm)
        if not agent:
            return "Error: Could not create ImageAgent"
        
        try:
            result = agent.chat(prompt, images=image_paths)
            return result
        except Exception as e:
            self.log(f"Image processing error: {e}", "error")
            return f"Error processing images: {e}"
    
    def execute(self, prompt: str = None, image_path: str = None, llm: str = None, **kwargs) -> str:
        """
        Execute image processing.
        
        Args:
            prompt: The prompt/question about the image
            image_path: Path to the image file (or comma-separated paths)
            llm: Optional LLM model name
            
        Returns:
            Agent's response
        """
        if not prompt:
            return "Error: No prompt provided"
        
        if not image_path:
            return "Error: No image path provided"
        
        # Handle multiple images (comma-separated)
        if ',' in image_path:
            paths = [p.strip() for p in image_path.split(',')]
            return self.process_multiple_images(prompt, paths, llm)
        
        return self.process_image(prompt, image_path, llm)
