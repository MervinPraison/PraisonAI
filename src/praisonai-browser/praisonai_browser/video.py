"""Video creation utility for browser automation recordings.

Creates videos from screenshot sequences captured during browser automation.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger("praisonai.browser.video")


def create_video_from_screenshots(
    screenshot_dir: str,
    output_path: Optional[str] = None,
    fps: int = 2,
    duration_per_frame: float = 0.5,
) -> Optional[str]:
    """Create a video/GIF from a directory of screenshots.
    
    Args:
        screenshot_dir: Directory containing step_*.png files
        output_path: Output video path (default: screenshot_dir/recording.gif)
        fps: Frames per second for the output
        duration_per_frame: Duration per frame in seconds (for GIF)
        
    Returns:
        Path to created video/GIF, or None if failed
    """
    screenshot_dir = Path(screenshot_dir)
    if not screenshot_dir.exists():
        logger.warning(f"Screenshot directory does not exist: {screenshot_dir}")
        return None
    
    # Find all step screenshots
    screenshots = sorted(screenshot_dir.glob("step_*.png"))
    if not screenshots:
        logger.warning(f"No screenshots found in {screenshot_dir}")
        return None
    
    logger.info(f"Found {len(screenshots)} screenshots to combine")
    
    # Default output path
    if output_path is None:
        output_path = str(screenshot_dir / "recording.gif")
    
    # Try using Pillow (most common)
    try:
        from PIL import Image
        
        # Load all frames
        frames = []
        for screenshot in screenshots:
            try:
                img = Image.open(screenshot)
                # Convert to RGB if necessary (GIF requirement)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Resize for smaller file size
                max_width = 1280
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_size = (max_width, int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                frames.append(img)
            except Exception as e:
                logger.warning(f"Failed to load {screenshot}: {e}")
        
        if not frames:
            logger.error("No frames could be loaded")
            return None
        
        # Save as GIF
        duration_ms = int(duration_per_frame * 1000)
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0,  # Infinite loop
            optimize=True,
        )
        
        logger.info(f"Created GIF: {output_path} ({len(frames)} frames)")
        return output_path
        
    except ImportError:
        logger.warning("Pillow not installed, trying imageio")
    
    # Fallback to imageio (if available)
    try:
        import imageio.v3 as iio
        
        frames = []
        for screenshot in screenshots:
            try:
                frame = iio.imread(screenshot)
                frames.append(frame)
            except Exception as e:
                logger.warning(f"Failed to load {screenshot}: {e}")
        
        if frames:
            # Create GIF
            iio.imwrite(output_path, frames, duration=duration_per_frame, loop=0)
            logger.info(f"Created GIF with imageio: {output_path}")
            return output_path
            
    except ImportError:
        logger.warning("imageio not installed")
    
    # Last resort: just return the screenshot directory path
    logger.warning("No image library available for video creation. Screenshots saved to: {screenshot_dir}")
    return None


def create_video_ffmpeg(
    screenshot_dir: str,
    output_path: str,
    fps: int = 2,
) -> Optional[str]:
    """Create video using ffmpeg (if available).
    
    Args:
        screenshot_dir: Directory containing step_*.png files
        output_path: Output video path (e.g. recording.mp4)
        fps: Frames per second
        
    Returns:
        Path to created video, or None if failed
    """
    import subprocess
    import shutil
    
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg not found in PATH")
        return None
    
    screenshot_dir = Path(screenshot_dir)
    pattern = str(screenshot_dir / "step_%03d.png")
    
    try:
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-framerate", str(fps),
            "-i", pattern,
            "-vf", "scale=1280:-2",  # Scale to 1280 width
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode == 0 and Path(output_path).exists():
            logger.info(f"Created video: {output_path}")
            return output_path
        else:
            logger.warning(f"ffmpeg failed: {result.stderr}")
            return None
            
    except Exception as e:
        logger.warning(f"ffmpeg error: {e}")
        return None


class FFmpegVideoEncoder:
    """Real-time video encoder using FFmpeg subprocess.
    
    Encodes frames streamed from CDP Page.startScreencast to WebM video.
    Uses VP9 codec for good quality and browser compatibility.
    
    Example:
        encoder = FFmpegVideoEncoder("/path/to/output.webm")
        encoder.start()
        for frame_data in cdp_screencast_frames:
            encoder.write_frame(frame_data)
        encoder.finish()
    """
    
    def __init__(
        self,
        output_path: str,
        fps: int = 10,
        width: int = 1280,
        height: int = 720,
        quality: str = "good",  # good, best, realtime
    ):
        """Initialize encoder.
        
        Args:
            output_path: Output video file path (should end in .webm or .mp4)
            fps: Target frames per second
            width: Video width
            height: Video height  
            quality: Encoding quality preset
        """
        import shutil
        
        self.output_path = output_path
        self.fps = fps
        self.width = width
        self.height = height
        self.quality = quality
        self.process = None
        self.frame_count = 0
        self._ffmpeg_available = shutil.which("ffmpeg") is not None
        self._started = False
        
    @property
    def available(self) -> bool:
        """Check if FFmpeg is available."""
        return self._ffmpeg_available
    
    def start(self) -> bool:
        """Start the FFmpeg encoding process.
        
        Returns:
            True if started successfully, False otherwise
        """
        if not self._ffmpeg_available:
            logger.warning("FFmpeg not available, video recording disabled")
            return False
        
        import subprocess
        
        # Determine output format from extension
        is_webm = self.output_path.endswith('.webm')
        
        try:
            if is_webm:
                # VP9 for WebM (good quality, browser compatible)
                cmd = [
                    "ffmpeg",
                    "-y",  # Overwrite output
                    "-f", "image2pipe",  # Read images from pipe
                    "-framerate", str(self.fps),
                    "-i", "-",  # Read from stdin
                    "-vf", f"scale={self.width}:-2",  # Scale maintaining aspect
                    "-c:v", "libvpx-vp9",  # VP9 codec
                    "-b:v", "1M",  # Bitrate
                    "-deadline", self.quality,
                    "-cpu-used", "4",  # Faster encoding
                    self.output_path,
                ]
            else:
                # H.264 for MP4
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "image2pipe",
                    "-framerate", str(self.fps),
                    "-i", "-",
                    "-vf", f"scale={self.width}:-2",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    self.output_path,
                ]
            
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._started = True
            logger.info(f"Started video recording to {self.output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start FFmpeg: {e}")
            return False
    
    def write_frame(self, frame_data: bytes) -> bool:
        """Write a frame to the video.
        
        Args:
            frame_data: JPEG or PNG image data
            
        Returns:
            True if written successfully
        """
        if not self._started or not self.process or not self.process.stdin:
            return False
        
        try:
            self.process.stdin.write(frame_data)
            self.frame_count += 1
            return True
        except Exception as e:
            logger.warning(f"Failed to write frame: {e}")
            return False
    
    def finish(self) -> Optional[str]:
        """Finish encoding and close the video file.
        
        Returns:
            Path to output video if successful, None otherwise
        """
        if not self._started or not self.process:
            return None
        
        try:
            self.process.stdin.close()
            self.process.wait(timeout=30)
            
            if self.process.returncode == 0:
                logger.info(f"Video saved: {self.output_path} ({self.frame_count} frames)")
                return self.output_path
            else:
                stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                logger.error(f"FFmpeg failed: {stderr[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Error finishing video: {e}")
            return None
        finally:
            self._started = False
            self.process = None


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available in PATH."""
    import shutil
    return shutil.which("ffmpeg") is not None
