"""
Multi-Agent Camera Analysis Example

This example demonstrates using multiple specialized agents to analyze
camera feeds from different perspectives (security, object detection, etc.).

Requirements:
    pip install praisonaiagents opencv-python

Usage:
    python camera-multi-agent.py

Environment Variables:
    OPENAI_API_KEY=your_openai_api_key
"""

import cv2
import os
from datetime import datetime
from praisonaiagents import Agent, Task, PraisonAIAgents


def capture_camera_frame(camera_id=0):
    """Capture a frame from camera"""
    cap = cv2.VideoCapture(camera_id)
    
    if not cap.isOpened():
        print(f"Error: Could not open camera {camera_id}")
        return None
        
    ret, frame = cap.read()
    cap.release()
    
    if ret:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = f"camera_frame_{timestamp}.jpg"
        cv2.imwrite(image_path, frame)
        return image_path
    
    return None


def analyze_with_multiple_agents():
    """Analyze camera feed using multiple specialized agents"""
    
    # Capture frame
    image_path = capture_camera_frame()
    if not image_path:
        print("Failed to capture camera frame")
        return None
    
    print(f"📸 Captured frame: {image_path}")
    
    # Create specialized agents
    security_agent = Agent(
        name="SecurityExpert",
        role="Security Specialist",
        goal="Identify security threats and suspicious activities",
        backstory="Expert security analyst with years of experience in surveillance and threat detection",
        llm="gpt-4o-mini"
    )
    
    object_detector = Agent(
        name="ObjectDetector",
        role="Object Recognition Specialist", 
        goal="Identify and catalog all objects in the scene",
        backstory="Computer vision expert specializing in object detection and classification",
        llm="gpt-4o-mini"
    )
    
    scene_analyst = Agent(
        name="SceneAnalyst",
        role="Scene Understanding Expert",
        goal="Provide comprehensive scene analysis and context",
        backstory="Environmental analyst expert in understanding spatial relationships and scene context",
        llm="gpt-4o-mini"
    )
    
    # Create specialized tasks
    security_task = Task(
        name="security_analysis",
        description="""Analyze this camera feed for security concerns:
        1. Identify any people and their activities
        2. Look for suspicious behavior or unauthorized access
        3. Check for potential security threats
        4. Assess overall security status of the area""",
        expected_output="Detailed security assessment with threat level and recommendations",
        agent=security_agent,
        images=[image_path]
    )
    
    object_task = Task(
        name="object_detection",
        description="""Identify and catalog all objects in this image:
        1. List all visible objects with their approximate locations
        2. Identify any vehicles, electronics, or valuable items
        3. Note any objects that seem out of place
        4. Provide a comprehensive inventory""",
        expected_output="Detailed object inventory with locations and descriptions",
        agent=object_detector,
        images=[image_path]
    )
    
    scene_task = Task(
        name="scene_analysis",
        description="""Provide comprehensive scene analysis:
        1. Describe the overall environment and setting
        2. Analyze lighting conditions and time of day
        3. Assess the general activity level and atmosphere
        4. Provide context about what type of location this appears to be""",
        expected_output="Complete scene description with environmental context",
        agent=scene_analyst,
        images=[image_path]
    )
    
    # Run multi-agent analysis
    agents = PraisonAIAgents(
        agents=[security_agent, object_detector, scene_analyst],
        tasks=[security_task, object_task, scene_task],
        process="parallel",  # Run all analyses in parallel
        verbose=1
    )
    
    result = agents.start()
    
    # Clean up temporary file
    if os.path.exists(image_path):
        os.remove(image_path)
    
    return result


def main():
    """Main function"""
    print("🎯 Starting multi-agent camera analysis...")
    print("📋 This will analyze the camera feed from multiple perspectives")
    
    result = analyze_with_multiple_agents()
    
    if result:
        print("\n" + "="*60)
        print("📊 MULTI-AGENT ANALYSIS RESULTS")
        print("="*60)
        
        # Display results by agent
        agent_names = {
            "security_analysis": "🛡️  SECURITY ANALYSIS",
            "object_detection": "🔍 OBJECT DETECTION", 
            "scene_analysis": "🌍 SCENE ANALYSIS"
        }
        
        for task_id, task_result in result["task_results"].items():
            print(f"\n{agent_names.get(task_id, f'Task {task_id}')}:")
            print("-" * 40)
            print(task_result.raw)
            
        print("\n" + "="*60)
        print("✅ Multi-agent analysis complete!")
    else:
        print("❌ Failed to complete camera analysis")


if __name__ == "__main__":
    main()