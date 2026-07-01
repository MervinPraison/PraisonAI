"""
Image Handler for CLI.

Provides two distinct image capabilities:
1. Image Description (Vision) - Analyze existing images using vision-capable LLMs
   Usage: praisonai "Describe this image" --image path/to/image.png

2. Image Generation - Generate new images from text prompts
   Usage: praisonai "A sunset over mountains" --image-generate
"""

import os
import base64
import logging
from typing import Any, Dict, Tuple, List, Optional
from .base import FlagHandler

logger = logging.getLogger(__name__)

# Supported image extensions for vision/description
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.tiff'}

# Default vision-capable models (gpt-4o has better vision support than gpt-4o-mini)
DEFAULT_VISION_MODEL = "gpt-4o"

# Default image generation models
DEFAULT_IMAGE_GEN_MODEL = "dall-e-3"
SUPPORTED_IMAGE_GEN_MODELS = [
    'gpt-image-1', 'gpt-image-1-mini', 'gpt-image-1.5', 
    'chatgpt-image-latest', 'dall-e-2', 'dall-e-3'
]


class ImageHandler(FlagHandler):
    """
    Handler for --image flag (Image Description/Vision).
    
    Describes/analyzes existing images using vision-capable LLMs like GPT-4o.
    This is for understanding what's IN an image, not generating new images.
    
    Example:
        praisonai "Describe this image" --image photo.png
        praisonai "What's in this image?" --image /path/to/image.jpg
        praisonai "Count the objects" --image image1.png,image2.png
    """
    
    @property
    def feature_name(self) -> str:
        return "image"
    
    @property
    def flag_name(self) -> str:
        return "image"
    
    @property
    def flag_help(self) -> str:
        return "Path to image file for vision-based description/analysis"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if litellm is available for vision."""
        try:
            import litellm
            return True, ""
        except ImportError:
            return False, "litellm not installed. Install with: pip install litellm"
    
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
    
    def _encode_image_to_base64(self, image_path: str) -> str:
        """Encode a local image file to base64."""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _get_image_mime_type(self, image_path: str) -> str:
        """Get MIME type based on file extension."""
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml',
            '.tiff': 'image/tiff',
        }
        return mime_types.get(ext, 'image/png')
    
    def _build_image_content(self, image_path: str) -> Dict[str, Any]:
        """Build image content for vision API."""
        if image_path.startswith(('http://', 'https://')):
            return {
                "type": "image_url",
                "image_url": {"url": image_path}
            }
        else:
            mime_type = self._get_image_mime_type(image_path)
            base64_data = self._encode_image_to_base64(image_path)
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
            }
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """Apply image configuration to agent config."""
        if flag_value:
            if isinstance(flag_value, str):
                config["images"] = [flag_value]
            elif isinstance(flag_value, list):
                config["images"] = flag_value
            config["use_vision"] = True
        return config
    
    def describe_image(self, prompt: str, image_path: str, llm = None) -> str:
        """
        Describe an image using vision-capable LLM.
        
        Args:
            prompt: The prompt/question about the image
            image_path: Path to the image file
            llm: Optional LLM model name (must be vision-capable), can be string or dict
            
        Returns:
            Description of the image
        """
        valid, msg = self.validate_image_path(image_path)
        if not valid:
            return f"Error: {msg}"
        
        available, dep_msg = self.check_dependencies()
        if not available:
            return f"Error: {dep_msg}"
        
        import litellm
        
        # Handle llm being a dict (from agent_config) or string
        if isinstance(llm, dict):
            model = llm.get('model', DEFAULT_VISION_MODEL)
        else:
            model = llm or DEFAULT_VISION_MODEL
        
        try:
            # Build message with image
            content = [
                {"type": "text", "text": prompt},
                self._build_image_content(image_path)
            ]
            
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": content}]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error describing image: {e}")
            return f"Error describing image: {e}"
    
    def describe_multiple_images(self, prompt: str, image_paths: List[str], llm = None) -> str:
        """
        Describe multiple images using vision-capable LLM.
        
        Args:
            prompt: The prompt/question about the images
            image_paths: List of paths to image files
            llm: Optional LLM model name, can be string or dict
            
        Returns:
            Description of the images
        """
        for path in image_paths:
            valid, msg = self.validate_image_path(path)
            if not valid:
                return f"Error: {msg}"
        
        available, dep_msg = self.check_dependencies()
        if not available:
            return f"Error: {dep_msg}"
        
        import litellm
        
        # Handle llm being a dict (from agent_config) or string
        if isinstance(llm, dict):
            model = llm.get('model', DEFAULT_VISION_MODEL)
        else:
            model = llm or DEFAULT_VISION_MODEL
        
        try:
            # Build message with all images
            content = [{"type": "text", "text": prompt}]
            for path in image_paths:
                content.append(self._build_image_content(path))
            
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": content}]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error describing images: {e}")
            return f"Error describing images: {e}"
    
    def execute(self, prompt: str = None, image_path: str = None, llm: str = None, **kwargs) -> str:
        """
        Execute image description (vision).
        
        Args:
            prompt: The prompt/question about the image
            image_path: Path to the image file (or comma-separated paths)
            llm: Optional vision-capable LLM model name
            
        Returns:
            Description of the image(s)
        """
        if not prompt:
            return "Error: No prompt provided"
        
        if not image_path:
            return "Error: No image path provided"
        
        # Handle multiple images (comma-separated)
        if ',' in image_path:
            paths = [p.strip() for p in image_path.split(',')]
            return self.describe_multiple_images(prompt, paths, llm)
        
        return self.describe_image(prompt, image_path, llm)


class ImageGenerateHandler(FlagHandler):
    """
    Handler for --image-generate flag (Image Generation).
    
    Generates NEW images from text prompts using DALL-E or similar models.
    This is for CREATING images, not analyzing existing ones.
    
    Example:
        praisonai "A sunset over mountains" --image-generate
        praisonai "A cat wearing a hat" --image-generate --llm dall-e-3
    """
    
    @property
    def feature_name(self) -> str:
        return "image_generate"
    
    @property
    def flag_name(self) -> str:
        return "image_generate"
    
    @property
    def flag_help(self) -> str:
        return "Generate an image from the text prompt"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if ImageAgent is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents") is not None:
                return True, ""
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
        except ImportError:
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """Apply image generation configuration."""
        if flag_value:
            config["use_image_generation"] = True
        return config
    
    def generate_image(self, prompt: str, llm: str = None, output_path: str = None) -> Dict[str, Any]:
        """
        Generate an image from a text prompt.
        
        Args:
            prompt: Text description of the image to generate
            llm: Image generation model (dall-e-3, dall-e-2, etc.)
            output_path: Optional path to save the generated image
            
        Returns:
            Dict with image URL or path, or error message
        """
        available, msg = self.check_dependencies()
        if not available:
            return {"error": msg}
        
        from praisonaiagents import ImageAgent
        
        # Use provided model or default
        model = llm or DEFAULT_IMAGE_GEN_MODEL
        
        # Validate model is supported for generation
        if model not in SUPPORTED_IMAGE_GEN_MODELS:
            return {
                "error": f"Invalid model: '{model}'. Supported image generation models: {', '.join(SUPPORTED_IMAGE_GEN_MODELS)}"
            }
        
        try:
            agent = ImageAgent(
                name="ImageGenerator",
                role="Image Generation Assistant",
                goal="Generate high-quality images from text descriptions",
                llm=model
            )
            
            result = agent.chat(prompt)
            
            # Save image if output path provided
            if output_path and isinstance(result, dict) and 'data' in result:
                self._save_image(result, output_path)
                result['saved_to'] = output_path
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return {"error": str(e)}
    
    def _save_image(self, result: Dict[str, Any], output_path: str) -> bool:
        """Save generated image to file."""
        try:
            import requests
            
            if 'data' in result and len(result['data']) > 0:
                image_data = result['data'][0]
                
                if 'url' in image_data:
                    # Download from URL
                    response = requests.get(image_data['url'])
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    return True
                elif 'b64_json' in image_data:
                    # Decode base64
                    import base64
                    img_bytes = base64.b64decode(image_data['b64_json'])
                    with open(output_path, 'wb') as f:
                        f.write(img_bytes)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error saving image: {e}")
            return False
    
    def execute(self, prompt: str = None, llm: str = None, output_path: str = None, **kwargs) -> Dict[str, Any]:
        """
        Execute image generation.
        
        Args:
            prompt: Text description of the image to generate
            llm: Image generation model name
            output_path: Optional path to save the image
            
        Returns:
            Dict with generated image info or error
        """
        if not prompt:
            return {"error": "No prompt provided for image generation"}
        
        return self.generate_image(prompt, llm, output_path)
