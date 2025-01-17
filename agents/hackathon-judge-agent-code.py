from praisonaiagents import Agent, Task, PraisonAIAgents
from pydantic import BaseModel
from typing import List, Dict
import os
import json

class ProjectEvaluation(BaseModel):
    innovation_score: int  # 0-100
    technical_complexity: int # 0-100  
    presentation_quality: int # 0-100
    user_experience: int # 0-100
    completeness: int # 0-100
    overall_score: int # 0-100
    key_strengths: List[str]
    areas_for_improvement: List[str]
    notable_features: List[str]
    technical_highlights: List[str]
    recommendations: List[str]
    market_potential: str
    scalability_assessment: str

# Create Vision Analysis Agent
hackathon_judge = Agent(
    name="HackathonJudge",
    role="Technical Project Evaluator",
    goal="Evaluate hackathon projects through video demonstrations",
    backstory="""You are an experienced hackathon judge and technical expert.
    You excel at evaluating innovation, technical implementation, and presentation quality.
    You provide constructive feedback and identify both strengths and areas for improvement.""",
    llm="gpt-4o-mini",  # Using vision-capable model
    self_reflect=False,
    knowledge=""
)

def evaluate_project(video_path: str) -> ProjectEvaluation:
    """
    Evaluate a hackathon project based on its video demonstration
    """
    evaluation_task = Task(
        name="project_evaluation",
        description="""Analyze this hackathon project video demonstration and provide a comprehensive evaluation:
        
        1. Score the following aspects (0-100):
           - Innovation and Creativity
           - Technical Complexity
           - Presentation Quality
           - User Experience
           - Project Completeness
           
        2. Identify:
           - Key strengths and standout features
           - Areas that could be improved
           - Notable technical implementations
           - Market potential and scalability
           
        3. Provide:
           - Specific recommendations for improvement
           - Technical suggestions
           - Potential future enhancements""",
        expected_output="Detailed project evaluation with scores and feedback",
        agent=hackathon_judge,
        output_pydantic=ProjectEvaluation,
        images=[video_path]  # Video input for multimodal analysis
    )

    # Initialize and run evaluation
    agents = PraisonAIAgents(
        agents=[hackathon_judge],
        tasks=[evaluation_task],
        process="sequential",
        verbose=True
    )
    
    response = agents.start()
    
    try:
        # If response contains task_results, extract the Pydantic model directly
        if isinstance(response, dict) and 'task_results' in response:
            task_output = response['task_results'][0]
            if hasattr(task_output, 'pydantic'):
                return task_output.pydantic
            elif hasattr(task_output, 'raw'):
                # Extract JSON from raw string if it's wrapped in ```json
                raw_text = task_output.raw
                if raw_text.startswith('```json'):
                    raw_text = raw_text.split('\n', 1)[1].rsplit('\n', 1)[0]
                evaluation_data = json.loads(raw_text)
            else:
                evaluation_data = json.loads(task_output) if isinstance(task_output, str) else task_output
        # If response is a string, try to parse it as JSON
        elif isinstance(response, str):
            evaluation_data = json.loads(response)
        # If response is a dict with task_status
        elif isinstance(response, dict) and 'task_status' in response:
            content = response['task_status']
            if isinstance(content, dict):
                evaluation_data = content
            else:
                evaluation_data = json.loads(content) if isinstance(content, str) else content
        else:
            evaluation_data = response
            
        print(f"Debug - Parsed evaluation_data: {evaluation_data}")
        
        # Create and return ProjectEvaluation instance
        return ProjectEvaluation(
            innovation_score=int(evaluation_data.get('innovation_score', 0)),
            technical_complexity=int(evaluation_data.get('technical_complexity', 0)),
            presentation_quality=int(evaluation_data.get('presentation_quality', 0)),
            user_experience=int(evaluation_data.get('user_experience', 0)),
            completeness=int(evaluation_data.get('completeness', 0)),
            overall_score=int(evaluation_data.get('overall_score', 0)),
            key_strengths=evaluation_data.get('key_strengths', []),
            areas_for_improvement=evaluation_data.get('areas_for_improvement', []),
            notable_features=evaluation_data.get('notable_features', []),
            technical_highlights=evaluation_data.get('technical_highlights', []),
            recommendations=evaluation_data.get('recommendations', []),
            market_potential=str(evaluation_data.get('market_potential', '')),
            scalability_assessment=str(evaluation_data.get('scalability_assessment', ''))
        )
    except Exception as e:
        print(f"Debug - Raw response: {response}")
        print(f"Error processing response: {e}")
        raise

if __name__ == "__main__":
    # Example usage
    current_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(current_dir, "presentation.mp4")
    result = evaluate_project(video_path)  # Now returns ProjectEvaluation directly
    
    print("\nHackathon Project Evaluation")
    print("===========================")
    print(f"\nOverall Score: {result.overall_score}/100")
    print("\nDetailed Scores:")
    print(f"Innovation: {result.innovation_score}/100")
    print(f"Technical Complexity: {result.technical_complexity}/100")
    print(f"Presentation: {result.presentation_quality}/100")
    print(f"User Experience: {result.user_experience}/100")
    print(f"Completeness: {result.completeness}/100")
    
    print("\nKey Strengths:")
    for strength in result.key_strengths:
        print(f"- {strength}")
        
    print("\nAreas for Improvement:")
    for area in result.areas_for_improvement:
        print(f"- {area}")
        
    print("\nTechnical Highlights:")
    for highlight in result.technical_highlights:
        print(f"- {highlight}")
        
    print("\nRecommendations:")
    for rec in result.recommendations:
        print(f"- {rec}")
        
    print(f"\nMarket Potential: {result.market_potential}")
    print(f"\nScalability Assessment: {result.scalability_assessment}") 