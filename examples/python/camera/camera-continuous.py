"""
Continuous Camera Monitoring Example

This example demonstrates continuous camera monitoring with periodic analysis
using PraisonAI vision agents. Perfect for security monitoring or real-time surveillance.

Requirements:
    pip install praisonaiagents opencv-python

Usage:
    python camera-continuous.py

Environment Variables:
    OPENAI_API_KEY=your_openai_api_key
"""

import cv2
import time
import os
from datetime import datetime
from praisonaiagents import Agent, Task, PraisonAIAgents


class ContinuousCameraMonitor:
    """Continuous camera monitoring system"""
    
    def __init__(self, camera_id=0, analysis_interval=10):
        """
        Initialize camera monitor
        
        Args:
            camera_id (int): Camera ID (0 for default)
            analysis_interval (int): Seconds between analyses
        """
        self.camera_id = camera_id
        self.analysis_interval = analysis_interval
        self.running = False
        
        # Create vision agent
        self.vision_agent = Agent(
            name="SecurityMonitor",
            role="Security Camera Analyst",
            goal="Monitor camera feeds for activities and security events",
            backstory="Expert security analyst with computer vision skills specialized in real-time monitoring",
            llm="gpt-4o-mini"
        )
    
    def capture_frame(self, cap):
        """Capture a single frame from camera"""
        ret, frame = cap.read()
        if ret:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"camera_capture_{timestamp}.jpg"
            cv2.imwrite(filename, frame)
            return filename
        return None
    
    def analyze_frame(self, image_path):
        """Analyze captured frame"""
        task = Task(
            name="monitor_camera_feed",
            description="""Monitor this camera feed for:
            1. Any people or unusual activities
            2. Objects that seem out of place
            3. Movement or changes in the scene
            4. Security-relevant events
            
            Provide a brief but detailed security report.""",
            expected_output="Security analysis report with timestamp and observations",
            agent=self.vision_agent,
            images=[image_path]
        )
        
        agents = PraisonAIAgents(
            agents=[self.vision_agent],
            tasks=[task],
            process="sequential",
            verbose=0  # Reduced verbosity for continuous monitoring
        )
        
        return agents.start()
    
    def start_monitoring(self):
        """Start continuous monitoring"""
        print(f"🎥 Starting continuous camera monitoring...")
        print(f"📊 Analysis interval: {self.analysis_interval} seconds")
        print("🛑 Press Ctrl+C to stop")
        
        cap = cv2.VideoCapture(self.camera_id)
        
        if not cap.isOpened():
            print(f"❌ Error: Could not open camera {self.camera_id}")
            return
        
        self.running = True
        
        try:
            while self.running:
                # Capture frame
                image_path = self.capture_frame(cap)
                
                if image_path:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"\n⏰ {timestamp} - Analyzing camera feed...")
                    
                    # Analyze frame
                    result = self.analyze_frame(image_path)
                    
                    # Display results
                    if result and "task_results" in result:
                        for task_id, task_result in result["task_results"].items():
                            print(f"📋 Security Report: {task_result.raw}")
                    
                    # Clean up temporary file
                    if os.path.exists(image_path):
                        os.remove(image_path)
                
                # Wait for next analysis
                time.sleep(self.analysis_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping camera monitoring...")
        finally:
            self.running = False
            cap.release()
            cv2.destroyAllWindows()
            print("✅ Camera monitoring stopped")


def main():
    """Main function"""
    # Configuration
    camera_id = 0  # Default camera
    analysis_interval = 15  # Analyze every 15 seconds
    
    # Create and start monitor
    monitor = ContinuousCameraMonitor(camera_id, analysis_interval)
    monitor.start_monitoring()


if __name__ == "__main__":
    main()