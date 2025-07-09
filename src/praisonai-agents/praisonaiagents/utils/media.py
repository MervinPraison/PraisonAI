"""Media processing utilities for handling images and videos.

This module provides utilities for processing media files including
base64 encoding and video frame extraction.
"""

import base64
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def encode_file_to_base64(file_path: str) -> str:
    """Base64-encode a file.
    
    Args:
        file_path: Path to the file to encode
        
    Returns:
        Base64-encoded string of the file contents
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        IOError: If the file cannot be read
    """
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error encoding file {file_path}: {str(e)}")
        raise IOError(f"Failed to encode file: {str(e)}")


def process_video(video_path: str, seconds_per_frame: float = 2.0) -> List[str]:
    """Split video into frames and return as base64-encoded images.
    
    This function extracts frames from a video at specified intervals
    and returns them as a list of base64-encoded JPEG images.
    
    Args:
        video_path: Path to the video file
        seconds_per_frame: Interval between frames to extract (default: 2.0 seconds)
        
    Returns:
        List of base64-encoded frames as strings
        
    Raises:
        ImportError: If cv2 (OpenCV) is not installed
        IOError: If the video file cannot be read
    """
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV (cv2) is not installed. Install with: pip install opencv-python")
        raise ImportError("OpenCV is required for video processing. Install with: pip install opencv-python")
    
    base64_frames = []
    
    try:
        video = cv2.VideoCapture(video_path)
        
        if not video.isOpened():
            raise IOError(f"Failed to open video file: {video_path}")
        
        total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = video.get(cv2.CAP_PROP_FPS)
        
        if fps <= 0:
            logger.warning(f"Invalid FPS ({fps}) for video {video_path}, using default 30 FPS")
            fps = 30.0
        
        frames_to_skip = int(fps * seconds_per_frame)
        if frames_to_skip < 1:
            frames_to_skip = 1
        
        curr_frame = 0
        extracted_count = 0
        
        while curr_frame < total_frames:
            video.set(cv2.CAP_PROP_POS_FRAMES, curr_frame)
            success, frame = video.read()
            
            if not success:
                break
            
            # Encode frame as JPEG
            success, buffer = cv2.imencode(".jpg", frame)
            if success:
                base64_frames.append(base64.b64encode(buffer).decode("utf-8"))
                extracted_count += 1
            else:
                logger.warning(f"Failed to encode frame {curr_frame}")
            
            curr_frame += frames_to_skip
        
        logger.info(f"Extracted {extracted_count} frames from video {video_path}")
        
    except Exception as e:
        logger.error(f"Error processing video {video_path}: {str(e)}")
        raise IOError(f"Failed to process video: {str(e)}")
    finally:
        if 'video' in locals():
            video.release()
    
    return base64_frames


def process_image(image_path: str, max_size: Optional[tuple] = None) -> str:
    """Process an image file and return as base64-encoded string.
    
    Args:
        image_path: Path to the image file
        max_size: Optional tuple (width, height) to resize image
        
    Returns:
        Base64-encoded image string
        
    Raises:
        ImportError: If PIL is not installed (when resizing is needed)
        IOError: If the image file cannot be read
    """
    if max_size is None:
        # No resizing needed, just encode
        return encode_file_to_base64(image_path)
    
    try:
        from PIL import Image
        import io
    except ImportError:
        logger.error("Pillow (PIL) is not installed. Install with: pip install Pillow")
        raise ImportError("Pillow is required for image resizing. Install with: pip install Pillow")
    
    try:
        # Open and resize image
        with Image.open(image_path) as img:
            # Convert RGBA to RGB if necessary
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            
            # Resize maintaining aspect ratio
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to bytes buffer
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            
            # Encode to base64
            return base64.b64encode(buffer.read()).decode("utf-8")
            
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {str(e)}")
        raise IOError(f"Failed to process image: {str(e)}")


__all__ = [
    'encode_file_to_base64',
    'process_video',
    'process_image',
]