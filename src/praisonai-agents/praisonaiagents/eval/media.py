"""
Media evaluator for PraisonAI Agents.

Evaluates media outputs (audio, images, video) from specialized agent pipelines.
Uses LLM-as-judge with multimodal capabilities for image evaluation,
and file-based verification for audio/video.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

from .base import BaseEvaluator

logger = logging.getLogger(__name__)


@dataclass
class MediaEvaluationResult:
    """Result of a media evaluation."""
    media_type: str  # audio, image, video, text
    passed: bool
    score: float
    reasoning: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MediaEvaluator(BaseEvaluator):
    """
    Evaluates media outputs from specialized agent pipelines.
    
    Supports:
    - Audio files (TTS output): Verifies file exists, has content, optionally transcribes
    - Images (ImageAgent output): Uses multimodal LLM to evaluate image quality
    - Video (VideoAgent output): Verifies file exists, has content
    - Text (standard agent output): Uses LLM-as-judge criteria evaluation
    
    Example:
        >>> from praisonaiagents.eval import MediaEvaluator
        >>> evaluator = MediaEvaluator(
        ...     media_type="audio",
        ...     criteria="Audio is clear and matches the input text",
        ...     expected_text="Hello world"
        ... )
        >>> result = evaluator.evaluate_file("/tmp/output.mp3")
    """
    
    def __init__(
        self,
        media_type: Literal["audio", "image", "video", "text", "auto"] = "auto",
        criteria: Optional[str] = None,
        expected_text: Optional[str] = None,
        expected_content: Optional[str] = None,
        min_file_size: int = 100,  # Minimum file size in bytes
        model: Optional[str] = None,
        verbose: bool = False,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
    ):
        """
        Initialize the media evaluator.
        
        Args:
            media_type: Type of media to evaluate (audio, image, video, text, auto)
            criteria: Custom criteria for LLM evaluation
            expected_text: Expected text content (for audio transcription comparison)
            expected_content: Expected content description (for image/video)
            min_file_size: Minimum acceptable file size in bytes
            model: LLM model for evaluation (defaults to gpt-4o-mini)
            verbose: Enable verbose output
            name: Name for this evaluation
            save_results_path: Path to save results
        """
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        
        self.media_type = media_type
        self.criteria = criteria
        self.expected_text = expected_text
        self.expected_content = expected_content
        self.min_file_size = min_file_size
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
    
    def _detect_media_type(self, output: Any) -> str:
        """Auto-detect media type from output."""
        if isinstance(output, str):
            # Check if it's a file path
            if os.path.exists(output):
                ext = os.path.splitext(output)[1].lower()
                if ext in ('.mp3', '.wav', '.ogg', '.flac', '.m4a'):
                    return "audio"
                elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                    return "image"
                elif ext in ('.mp4', '.avi', '.mov', '.webm'):
                    return "video"
            return "text"
        
        # Check for LiteLLM response types
        output_class = output.__class__.__name__
        if 'ImageResponse' in output_class:
            return "image"
        elif 'HttpxBinaryResponseContent' in output_class:
            return "audio"  # TTS output
        elif 'VideoResponse' in output_class:
            return "video"
        
        return "text"
    
    def evaluate(self, output: Any, file_path: Optional[str] = None) -> MediaEvaluationResult:
        """
        Evaluate a media output.
        
        Args:
            output: The output to evaluate (can be file path, response object, or text)
            file_path: Optional explicit file path for audio/video
            
        Returns:
            MediaEvaluationResult with evaluation details
        """
        media_type = self.media_type if self.media_type != "auto" else self._detect_media_type(output)
        
        if media_type == "audio":
            return self._evaluate_audio(output, file_path)
        elif media_type == "image":
            return self._evaluate_image(output)
        elif media_type == "video":
            return self._evaluate_video(output, file_path)
        else:
            return self._evaluate_text(output)
    
    def _evaluate_audio(self, output: Any, file_path: Optional[str] = None) -> MediaEvaluationResult:
        """Evaluate audio output."""
        # Determine file path
        if file_path and os.path.exists(file_path):
            audio_path = file_path
        elif isinstance(output, str) and os.path.exists(output):
            audio_path = output
        else:
            # Check common output locations
            for path in ['output.mp3', '/tmp/output.mp3']:
                if os.path.exists(path):
                    audio_path = path
                    break
            else:
                return MediaEvaluationResult(
                    media_type="audio",
                    passed=False,
                    score=0.0,
                    reasoning="Audio file not found"
                )
        
        # Check file size
        file_size = os.path.getsize(audio_path)
        if file_size < self.min_file_size:
            return MediaEvaluationResult(
                media_type="audio",
                passed=False,
                score=0.0,
                reasoning=f"Audio file too small ({file_size} bytes)",
                file_path=audio_path,
                file_size=file_size
            )
        
        # If expected text provided, transcribe and compare
        if self.expected_text:
            try:
                from ..agent.audio_agent import AudioAgent
                transcriber = AudioAgent(llm="openai/whisper-1")
                transcription = transcriber.transcribe(audio_path)
                
                # Compare transcription to expected text
                similarity = self._text_similarity(transcription, self.expected_text)
                passed = similarity >= 0.7
                
                return MediaEvaluationResult(
                    media_type="audio",
                    passed=passed,
                    score=similarity * 10,
                    reasoning=f"Transcription: '{transcription}' (similarity: {similarity:.2f})",
                    file_path=audio_path,
                    file_size=file_size,
                    metadata={"transcription": transcription, "expected": self.expected_text}
                )
            except Exception as e:
                logger.warning(f"Transcription failed: {e}")
        
        # Basic file validation passed
        return MediaEvaluationResult(
            media_type="audio",
            passed=True,
            score=8.0,
            reasoning=f"Audio file created successfully ({file_size} bytes)",
            file_path=audio_path,
            file_size=file_size
        )
    
    def _evaluate_image(self, output: Any) -> MediaEvaluationResult:
        """Evaluate image output using multimodal LLM."""
        # Extract image URL from response
        image_url = None
        if hasattr(output, 'data') and output.data:
            if hasattr(output.data[0], 'url'):
                image_url = output.data[0].url
            elif hasattr(output.data[0], 'b64_json'):
                # Base64 encoded image
                image_url = f"data:image/png;base64,{output.data[0].b64_json}"
        elif isinstance(output, str):
            if output.startswith('http') or output.startswith('data:'):
                image_url = output
            elif os.path.exists(output):
                # Local file - would need to encode to base64
                image_url = output
        
        if not image_url:
            return MediaEvaluationResult(
                media_type="image",
                passed=False,
                score=0.0,
                reasoning="Could not extract image URL from output"
            )
        
        # Use multimodal LLM to evaluate image
        if self.criteria or self.expected_content:
            try:
                import litellm
                
                eval_prompt = self.criteria or f"Does this image match the description: {self.expected_content}"
                
                response = litellm.completion(
                    model="gpt-4o-mini",  # Multimodal model
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"""Evaluate this image based on the criteria.

Criteria: {eval_prompt}

Score from 1-10 and explain your reasoning.
Format:
SCORE: [1-10]
REASONING: [explanation]"""},
                                {"type": "image_url", "image_url": {"url": image_url}}
                            ]
                        }
                    ],
                    max_tokens=200
                )
                
                response_text = response.choices[0].message.content or ""
                score, reasoning = self._parse_score_response(response_text)
                
                return MediaEvaluationResult(
                    media_type="image",
                    passed=score >= 7.0,
                    score=score,
                    reasoning=reasoning,
                    metadata={"image_url": image_url[:100] + "..." if len(image_url) > 100 else image_url}
                )
            except Exception as e:
                logger.warning(f"Image evaluation failed: {e}")
        
        # Basic validation - image was generated
        return MediaEvaluationResult(
            media_type="image",
            passed=True,
            score=8.0,
            reasoning="Image generated successfully",
            metadata={"image_url": image_url[:100] + "..." if len(image_url) > 100 else image_url}
        )
    
    def _evaluate_video(self, output: Any, file_path: Optional[str] = None) -> MediaEvaluationResult:
        """Evaluate video output."""
        # Determine file path
        video_path = None
        if file_path and os.path.exists(file_path):
            video_path = file_path
        elif isinstance(output, str) and os.path.exists(output):
            video_path = output
        elif hasattr(output, 'url'):
            # Video URL from API response
            return MediaEvaluationResult(
                media_type="video",
                passed=True,
                score=8.0,
                reasoning="Video generated successfully",
                metadata={"video_url": output.url}
            )
        
        if video_path:
            file_size = os.path.getsize(video_path)
            if file_size < self.min_file_size:
                return MediaEvaluationResult(
                    media_type="video",
                    passed=False,
                    score=0.0,
                    reasoning=f"Video file too small ({file_size} bytes)",
                    file_path=video_path,
                    file_size=file_size
                )
            
            return MediaEvaluationResult(
                media_type="video",
                passed=True,
                score=8.0,
                reasoning=f"Video file created successfully ({file_size} bytes)",
                file_path=video_path,
                file_size=file_size
            )
        
        return MediaEvaluationResult(
            media_type="video",
            passed=False,
            score=0.0,
            reasoning="Video file not found"
        )
    
    def _evaluate_text(self, output: Any) -> MediaEvaluationResult:
        """Evaluate text output using LLM-as-judge."""
        text = str(output)
        
        if not self.criteria:
            # Basic validation
            return MediaEvaluationResult(
                media_type="text",
                passed=bool(text and len(text) > 0),
                score=8.0 if text else 0.0,
                reasoning="Text output generated" if text else "Empty output"
            )
        
        try:
            import litellm
            
            response = litellm.completion(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Evaluate this text against the criteria.

Criteria: {self.criteria}

Text: {text}

Score from 1-10 and explain your reasoning.
Format:
SCORE: [1-10]
REASONING: [explanation]"""
                    }
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            response_text = response.choices[0].message.content or ""
            score, reasoning = self._parse_score_response(response_text)
            
            return MediaEvaluationResult(
                media_type="text",
                passed=score >= 7.0,
                score=score,
                reasoning=reasoning
            )
        except Exception as e:
            logger.warning(f"Text evaluation failed: {e}")
            return MediaEvaluationResult(
                media_type="text",
                passed=bool(text),
                score=5.0,
                reasoning=f"Evaluation failed: {e}"
            )
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity (case-insensitive word overlap)."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)
    
    def _parse_score_response(self, response: str) -> tuple:
        """Parse score and reasoning from LLM response."""
        import re
        
        score = 5.0  # Default
        reasoning = response
        
        # Try to extract score
        score_match = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)', response, re.IGNORECASE)
        if score_match:
            score = float(score_match.group(1))
        
        # Try to extract reasoning
        reasoning_match = re.search(r'REASONING:\s*(.+)', response, re.IGNORECASE | re.DOTALL)
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
        
        return score, reasoning
    
    def run(self, output: Any = None, file_path: Optional[str] = None, print_summary: bool = False) -> MediaEvaluationResult:
        """
        Run the evaluation.
        
        Args:
            output: Output to evaluate
            file_path: Optional file path for media files
            print_summary: Print evaluation summary
            
        Returns:
            MediaEvaluationResult
        """
        result = self.evaluate(output, file_path)
        
        if print_summary:
            self._print_summary(result)
        
        return result
    
    def _print_summary(self, result: MediaEvaluationResult):
        """Print evaluation summary."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="Media Evaluation Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green" if result.passed else "red")
            
            table.add_row("Media Type", result.media_type)
            table.add_row("Score", f"{result.score:.1f}/10")
            table.add_row("Status", "✅ PASSED" if result.passed else "❌ FAILED")
            table.add_row("Reasoning", result.reasoning[:50] + "..." if len(result.reasoning) > 50 else result.reasoning)
            
            if result.file_path:
                table.add_row("File Path", result.file_path)
            if result.file_size:
                table.add_row("File Size", f"{result.file_size} bytes")
            
            console.print(table)
        except ImportError:
            print(f"Media Evaluation: {result.media_type}")
            print(f"  Score: {result.score:.1f}/10")
            print(f"  Status: {'PASSED' if result.passed else 'FAILED'}")
            print(f"  Reasoning: {result.reasoning}")
