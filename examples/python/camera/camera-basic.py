# praisonai: skip=true
"""
Basic Camera Integration Example

This example demonstrates how to capture a single frame from a camera
and analyze it using a PraisonAI vision agent.

Requirements:
    pip install praisonaiagents opencv-python

Usage:
    python camera-basic.py

Environment Variables:
    OPENAI_API_KEY=your_openai_api_key
"""

import cv2
import os
from praisonaiagents import Agent, Task, AgentTeam


def capture_and_analyze():
    """Capture a single frame from camera and analyze it"""
    
    # Create vision agent
    vision_agent = Agent(
        name="CameraAnalyst",
        role="Camera Feed Analyzer",
        goal="Analyze camera captures in real-time",
        backstory="Expert in real-time visual analysis with computer vision skills",
        llm="gpt-4o-mini"
    )
    
    # Initialize camera (0 for default camera)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open camera")
        return None
        
    try:
        # Capture frame
        ret, frame = cap.read()
        
        if ret:
            # Save frame temporarily
            image_path = "temp_camera_capture.jpg"
            cv2.imwrite(image_path, frame)
            print(f"Frame captured and saved as {image_path}")
            
            # Create analysis task
            task = Task(
                name="analyze_camera_feed",
                description="Analyze what you see in this camera capture. Identify objects, people, and activities.",
                expected_output="Detailed analysis of the camera content including objects, people, activities, and overall scene description",
                agent=vision_agent,
                images=[image_path]
            )
            
            # Run analysis
            agents = AgentTeam(
                agents=[vision_agent],
                tasks=[task],
                process="sequential",
            )
            
            result = agents.start()
            
            # Clean up temporary file
            if os.path.exists(image_path):
                os.remove(image_path)
                
            return result
            
        else:
            print("Error: Could not capture frame")
            return None
            
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main():
    """Main function"""
    print("📸 Starting basic camera analysis...")
    print("Make sure your camera is connected and accessible")
    
    result = capture_and_analyze()
    
    if result:
        print("\n🔍 Analysis Results:")
        task_results = result.get("task_results") if isinstance(result, dict) else result
        if isinstance(task_results, dict):
            iterable = task_results.items()
        elif isinstance(task_results, list):
            iterable = enumerate(task_results)
        else:
            iterable = [("result", task_results)]

        for task_id, task_result in iterable:
            print(f"\nTask {task_id}:")
            raw_value = getattr(task_result, "raw", None)
            print(raw_value if raw_value is not None else str(task_result))
    else:
        print("❌ Failed to capture and analyze camera feed")


if __name__ == "__main__":
    main()