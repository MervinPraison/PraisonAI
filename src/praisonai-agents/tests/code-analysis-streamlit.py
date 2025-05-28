import streamlit as st
from praisonaiagents import Agent, Task, PraisonAIAgents
from pydantic import BaseModel
from typing import List, Dict, Any
from gitingest import ingest

# Import the same classes and code from code-analysis-agents.py
class CodeMetrics(BaseModel):
    category: str
    score: int
    findings: List[str]

class CodeAnalysisReport(BaseModel):
    overall_quality: int
    code_metrics: List[CodeMetrics]
    architecture_score: int
    maintainability_score: int
    performance_score: int
    security_score: int
    test_coverage: int
    key_strengths: List[str]
    improvement_areas: List[str]
    tech_stack: List[str]
    recommendations: List[str]
    complexity_metrics: Dict[str, int]
    best_practices: List[Dict[str, str]]
    potential_risks: List[str]
    documentation_quality: int

def analyze_code(code_source: str) -> CodeAnalysisReport:
    """
    Analyze code from directory path or GitHub URL
    """
    # Create code analyzer agent
    code_analyzer = Agent(
        role="Code Analysis Expert",
        goal="Provide comprehensive code evaluation and recommendations",
        backstory="""Expert code analyst specializing in architecture review, 
        best practices, and technical debt assessment.""",
        verbose=True
    )

    # Create analysis task
    code_analysis_task = Task(
        description="""Analyze code repository and provide structured evaluation:
        
        1. Overall Quality (0-100)
        2. Core Metrics Analysis:
           - Architecture and Design
           - Code Maintainability
           - Performance Optimization
           - Security Practices
           - Test Coverage
        3. Technical Assessment:
           - Technology Stack Review
           - Code Complexity Analysis
           - Best Practices Adherence
           - Risk Assessment
        4. Recommendations:
           - Key Improvements
           - Architecture Suggestions
           - Security Enhancements""",
        expected_output="Detailed code analysis report with metrics and recommendations",
        agent=code_analyzer,
        output_pydantic=CodeAnalysisReport
    )

    # Ingest code content
    summary, tree, content = ingest(code_source)
    
    # Concatenate context into structured format
    context_text = f"""
    CODE REPOSITORY ANALYSIS
    =======================
    
    SUMMARY
    -------
    {summary}
    
    REPOSITORY STRUCTURE
    -------------------
    {tree}
    
    SOURCE CODE
    -----------
    {content}
    """
    
    # Initialize and run analysis
    agents = PraisonAIAgents(
        agents=[code_analyzer],
        tasks=[code_analysis_task]
    )
    
    result = agents.start(context_text)
    
    # Extract the Pydantic model from the result
    if isinstance(result, dict) and 'task_results' in result:
        # Get the first task result's pydantic output
        analysis_result = result['task_results'][0].pydantic
        if isinstance(analysis_result, CodeAnalysisReport):
            return analysis_result
    
    # If we can't get the Pydantic model, create one from the raw data
    return CodeAnalysisReport(**result)

def display_code_metrics(metrics, cols):
    """Display code metrics in columns with color-coded scores"""
    for i, metric in enumerate(metrics):
        score = metric.score
        color = "red" if score < 60 else "orange" if score < 75 else "green"
        
        # Use modulo to alternate between columns
        with cols[i % len(cols)]:
            st.markdown(f"### {metric.category}")
            st.markdown(f"**Score:** :{color}[{score}%]")
            for finding in metric.findings:
                st.markdown(f"• {finding}")

def display_section(title: str, items: list, icon: str = "•"):
    """Display a section with items in a consistent format"""
    st.markdown(f"### {title}")
    for item in items:
        if isinstance(item, dict):
            for key, value in item.items():
                st.markdown(f"{icon} **{key}**: {value}")
        else:
            st.markdown(f"{icon} {item}")

def main():
    st.set_page_config(
        page_title="Code Analysis Agent",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("Code Analysis Agent")
    
    with st.sidebar:
        st.header("Input")
        code_source = st.text_input(
            "GitHub URL or Local Path",
            placeholder="https://github.com/username/repo or /path/to/directory"
        )
        analyze_button = st.button("Analyze Code", type="primary")
    
    if analyze_button and code_source:
        try:
            with st.spinner("Analyzing code..."):
                result = analyze_code(code_source)
                
                # Overall Metrics
                st.header("Overall Metrics")
                cols = st.columns(6)
                metrics = {
                    "Overall Quality": result.overall_quality,
                    "Architecture": result.architecture_score,
                    "Maintainability": result.maintainability_score,
                    "Performance": result.performance_score,
                    "Security": result.security_score,
                    "Test Coverage": result.test_coverage
                }
                
                for (metric, value), col in zip(metrics.items(), cols):
                    color = "red" if value < 60 else "orange" if value < 75 else "green"
                    col.metric(metric, f"{value}%")
                    col.markdown(f":{color}[{'●' * (value // 20)}]")
                
                # Detailed Analysis
                st.header("Detailed Analysis")
                metric_cols = st.columns(2)
                display_code_metrics(result.code_metrics, metric_cols)
                
                # Technology Stack
                col1, col2 = st.columns(2)
                with col1:
                    st.header("Technology Stack")
                    for tech in result.tech_stack:
                        st.markdown(f"🔧 {tech}")
                
                with col2:
                    st.header("Complexity Metrics")
                    for metric, value in result.complexity_metrics.items():
                        st.metric(metric.replace('_', ' ').title(), value)
                
                # Key Findings
                st.header("Key Findings")
                cols = st.columns(2)
                
                with cols[0]:
                    display_section("✅ Strengths", result.key_strengths)
                    display_section("🔄 Best Practices", result.best_practices)
                
                with cols[1]:
                    display_section("⚠️ Areas for Improvement", result.improvement_areas)
                    display_section("❗ Potential Risks", result.potential_risks)
                
                # Recommendations
                st.header("Recommendations")
                for i, rec in enumerate(result.recommendations, 1):
                    st.markdown(f"**{i}.** {rec}")
                
                # Documentation Quality
                st.header("Documentation")
                doc_score = result.documentation_quality
                color = "red" if doc_score < 60 else "orange" if doc_score < 75 else "green"
                st.markdown(f"Documentation Quality: :{color}[{doc_score}%]")
                
        except Exception as e:
            st.error(f"Error analyzing code: {str(e)}")
            st.exception(e)
    
    elif analyze_button:
        st.warning("Please enter a GitHub URL or local path")

if __name__ == "__main__":
    main() 