import streamlit as st
from praisonaiagents import Agent, Task, PraisonAIAgents
from pydantic import BaseModel
from typing import List, Dict
import json
import asyncio
import nest_asyncio
from functools import partial

# Enable nested event loops
nest_asyncio.apply()

class SkillMetrics(BaseModel):
    name: str
    score: int
    comments: str

class CVAnalysisReport(BaseModel):
    overall_score: int
    skill_metrics: List[SkillMetrics]
    experience_score: int
    education_score: int
    presentation_score: int
    achievement_impact_score: int
    market_readiness: int
    key_strengths: List[str]
    areas_for_improvement: List[str]
    market_fit: str
    recommendations: List[str]
    technical_skills: List[Dict[str, int]]
    soft_skills: List[Dict[str, int]]
    skill_gaps: List[str]
    key_achievements: List[str]
    impact_metrics: List[Dict[str, str]]
    areas_of_expertise: List[str]

async def analyze_cv_async(cv_content):
    cv_analyzer = Agent(
        role="CV Analysis Expert",
        goal="Provide comprehensive CV evaluation and recommendations",
        backstory="""You are an expert CV analyst with deep knowledge of industry requirements, 
        market trends, and talent assessment. You excel at evaluating skills, experience, 
        and providing actionable recommendations.""",
        verbose=True
    )

    cv_analysis_task = Task(
        description="""Perform a detailed CV analysis with scoring metrics and provide output in the following format:
        1. Overall Score (0-100):
           - Calculate based on weighted average of all metrics
        
        2. Individual Skill Metrics:
           - For each major skill found in CV:
             * Name of skill
             * Score (0-100)
             * Specific feedback/comments
        
        3. Core Metrics (0-100 each):
           - Experience Score: Based on relevance and years
           - Education Score: Based on relevance and level
           - Presentation Score: CV format, clarity, structure
           - Achievement Impact Score: Measurable results
           - Market Readiness: Current market fit
        
        4. Technical Skills:
           - List each skill with proficiency score (0-100)
        
        5. Soft Skills:
           - List each skill with proficiency score (0-100)
        
        6. Detailed Analysis sections
        
        7. Recommendations:
           - 3-5 actionable steps for improvement""",
        expected_output="Structured CV analysis report with detailed metrics and scoring justification",
        agent=cv_analyzer,
        output_pydantic=CVAnalysisReport
    )

    agents = PraisonAIAgents(
        agents=[cv_analyzer],
        tasks=[cv_analysis_task]
    )

    try:
        result = await agents.astart(cv_content)
        return result['task_results'][0].pydantic
    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        raise e

def analyze_cv(cv_content):
    async def run_analysis():
        return await analyze_cv_async(cv_content)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_analysis())
        return result
    except Exception as e:
        raise e
    finally:
        loop.close()

def main():
    st.set_page_config(page_title="CV Analyzer", layout="wide")
    st.title("Professional CV Analyzer")
    
    # File upload
    cv_file = st.file_uploader("Upload your CV (TXT format)", type=['txt'])
    
    if cv_file:
        cv_content = cv_file.read().decode()
        
        with st.spinner('Analyzing your CV...'):
            try:
                analysis = analyze_cv(cv_content)
                
                # Display Overall Score
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Overall Score", f"{analysis.overall_score}/100")
                with col2:
                    st.metric("Market Readiness", f"{analysis.market_readiness}/100")
                with col3:
                    st.metric("Experience Score", f"{analysis.experience_score}/100")

                # Core Metrics
                st.subheader("Core Metrics")
                metrics_cols = st.columns(4)
                with metrics_cols[0]:
                    st.metric("Education", f"{analysis.education_score}/100")
                with metrics_cols[1]:
                    st.metric("Presentation", f"{analysis.presentation_score}/100")
                with metrics_cols[2]:
                    st.metric("Achievement Impact", f"{analysis.achievement_impact_score}/100")
                with metrics_cols[3]:
                    st.metric("Market Readiness", f"{analysis.market_readiness}/100")

                # Skill Metrics
                st.subheader("Detailed Skill Analysis")
                for skill in analysis.skill_metrics:
                    with st.expander(f"{skill.name} - Score: {skill.score}/100"):
                        st.write(skill.comments)

                # Technical and Soft Skills
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Technical Skills")
                    for skill in analysis.technical_skills:
                        for skill_name, score in skill.items():
                            st.progress(score/100)
                            st.caption(f"{skill_name}: {score}/100")
                
                with col2:
                    st.subheader("Soft Skills")
                    for skill in analysis.soft_skills:
                        for skill_name, score in skill.items():
                            st.progress(score/100)
                            st.caption(f"{skill_name}: {score}/100")

                # Key Information
                st.subheader("Key Analysis")
                col1, col2 = st.columns(2)
                with col1:
                    st.write("🎯 Key Strengths")
                    for strength in analysis.key_strengths:
                        st.write(f"• {strength}")
                    
                    st.write("🎮 Areas of Expertise")
                    for expertise in analysis.areas_of_expertise:
                        st.write(f"• {expertise}")

                with col2:
                    st.write("🔄 Areas for Improvement")
                    for area in analysis.areas_for_improvement:
                        st.write(f"• {area}")
                    
                    st.write("⚠️ Skill Gaps")
                    for gap in analysis.skill_gaps:
                        st.write(f"• {gap}")

                # Impact Metrics
                st.subheader("Impact Metrics")
                for metric in analysis.impact_metrics:
                    for key, value in metric.items():
                        st.metric(key, value)

                # Recommendations
                st.subheader("📋 Recommendations")
                for rec in analysis.recommendations:
                    st.write(f"• {rec}")

            except Exception as e:
                st.error(f"An error occurred during analysis: {str(e)}")
    
    else:
        st.info("Please upload your CV in TXT format to begin the analysis")

if __name__ == "__main__":
    main()