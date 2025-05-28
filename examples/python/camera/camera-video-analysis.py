"""
Camera Video Recording and Analysis Example

This example demonstrates recording video segments from camera
and analyzing them using PraisonAI vision agents.

Requirements:
    pip install praisonaiagents opencv-python

Usage:
    python camera-video-analysis.py

Environment Variables:
    OPENAI_API_KEY=your_openai_api_key
"""

import cv2
import os
import time
from datetime import datetime
from praisonaiagents import Agent, Task, PraisonAIAgents


class CameraVideoAnalyzer:
    """Camera video recording and analysis system"""
    
    def __init__(self, camera_id=0):
        """
        Initialize video analyzer
        
        Args:
            camera_id (int): Camera ID (0 for default)
        """
        self.camera_id = camera_id
        
        # Create video analysis agent
        self.video_agent = Agent(
            name="VideoAnalyst",
            role="Video Content Analyzer",
            goal="Analyze video content for activities, objects, and events",
            backstory="Expert in video analysis and temporal event detection with computer vision expertise",
            llm="gpt-4o-mini"
        )
    
    def record_video_segment(self, duration_seconds=10):
        """
        Record a video segment from camera
        
        Args:
            duration_seconds (int): Length of video to record
            
        Returns:
            str: Path to recorded video file or None if failed
        """
        cap = cv2.VideoCapture(self.camera_id)
        
        if not cap.isOpened():
            print(f"Error: Could not open camera {self.camera_id}")
            return None
        
        # Get video properties
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Setup video writer
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_path = f"camera_recording_{timestamp}.mp4"
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
        
        print(f"🎬 Recording video for {duration_seconds} seconds...")
        print(f"📹 Resolution: {width}x{height}, FPS: {fps}")
        
        start_time = time.time()
        frame_count = 0
        
        try:
            while (time.time() - start_time) < duration_seconds:
                ret, frame = cap.read()
                
                if ret:
                    out.write(frame)
                    frame_count += 1
                    
                    # Show recording indicator
                    if frame_count % fps == 0:  # Update every second
                        elapsed = int(time.time() - start_time)
                        remaining = duration_seconds - elapsed
                        print(f"⏱️  Recording... {remaining}s remaining")
                else:
                    break
                    
        finally:
            cap.release()
            out.release()
            cv2.destroyAllWindows()
        
        if frame_count > 0:
            print(f"✅ Video recorded: {video_path} ({frame_count} frames)")
            return video_path
        else:
            print("❌ Failed to record video")
            if os.path.exists(video_path):
                os.remove(video_path)
            return None
    
    def analyze_video(self, video_path):
        """
        Analyze recorded video
        
        Args:
            video_path (str): Path to video file
            
        Returns:
            dict: Analysis results
        """
        task = Task(
            name="analyze_video_content",
            description="""Analyze this video recording and provide:
            1. Summary of main activities and events observed
            2. Timeline of key moments or changes
            3. Identification of people, objects, and movements
            4. Any notable interactions or behaviors
            5. Overall assessment of what happened in the video
            
            Focus on providing a comprehensive temporal analysis.""",
            expected_output="Detailed video analysis with timeline and event description",
            agent=self.video_agent,
            images=[video_path]  # PraisonAI supports video files in images parameter
        )
        
        agents = PraisonAIAgents(
            agents=[self.video_agent],
            tasks=[task],
            process="sequential",
            verbose=1
        )
        
        return agents.start()
    
    def record_and_analyze(self, duration=10):
        """
        Record video and analyze it
        
        Args:
            duration (int): Recording duration in seconds
        """
        # Record video
        video_path = self.record_video_segment(duration)
        
        if not video_path:
            return None
        
        print(f"\n🔍 Analyzing recorded video...")
        
        # Analyze video
        result = self.analyze_video(video_path)
        
        # Clean up video file
        if os.path.exists(video_path):
            os.remove(video_path)
            print(f"🗑️  Cleaned up temporary video file")
        
        return result


def main():
    """Main function"""
    print("🎥 Camera Video Recording and Analysis")
    print("=" * 50)
    
    # Configuration
    camera_id = 0
    recording_duration = 15  # seconds
    
    print(f"📹 Camera: {camera_id}")
    print(f"⏱️  Recording Duration: {recording_duration} seconds")
    print("\nMake sure your camera is connected and accessible")
    print("The system will record a video segment and then analyze it")
    
    input("\nPress Enter to start recording...")
    
    # Create analyzer and run
    analyzer = CameraVideoAnalyzer(camera_id)
    result = analyzer.record_and_analyze(recording_duration)
    
    if result:
        print("\n" + "="*60)
        print("📊 VIDEO ANALYSIS RESULTS")
        print("="*60)
        
        for task_id, task_result in result["task_results"].items():
            print(f"\nTask: {task_id}")
            print("-" * 40)
            print(task_result.raw)
        
        print("\n" + "="*60)
        print("✅ Video analysis complete!")
    else:
        print("❌ Failed to record and analyze video")


if __name__ == "__main__":
    main()