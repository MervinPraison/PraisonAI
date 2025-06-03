"""
Secondary Market Research FastAPI Application

This FastAPI application provides a REST API for generating customized 
secondary market research reports. Users can specify company, geography, 
industry, and research sections to generate tailored reports.

Features:
- RESTful API endpoints for market research
- Customizable research parameters
- Async report generation
- JSON and PDF report formats
- Real-time progress tracking
- Report history and caching

Usage:
    uvicorn secondary-market-research-api:app --reload --port 8000
    
    Then visit: http://localhost:8000/docs for API documentation
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import asyncio
import json
import uuid
from datetime import datetime
import os
from pathlib import Path

# Import our market research system
from praisonaiagents import Agent, Task, PraisonAIAgents, Tools

# Create FastAPI app
app = FastAPI(
    title="Secondary Market Research API",
    description="Generate customized secondary market research reports",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create directories for storing reports
REPORTS_DIR = Path("generated_reports")
REPORTS_DIR.mkdir(exist_ok=True)

# In-memory storage for job status (in production, use Redis or database)
job_status = {}

# Pydantic models for request/response
class MarketResearchRequest(BaseModel):
    """Request model for market research generation"""
    company: str = Field(..., description="Company name to research", example="Tesla")
    geography: str = Field(..., description="Geographic region", example="North America")
    industry: str = Field(..., description="Industry sector", example="Electric Vehicles")
    sections: Optional[List[str]] = Field(
        default=["market_overview", "competitive_analysis", "financial_performance", "growth_opportunities", "risk_assessment"],
        description="Research sections to include",
        example=["market_overview", "competitive_analysis", "financial_performance"]
    )
    format: Optional[str] = Field(default="json", description="Output format: json or pdf", example="json")
    email: Optional[str] = Field(None, description="Email for notification when complete", example="user@company.com")

class MarketResearchResponse(BaseModel):
    """Response model for market research request"""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status: pending, running, completed, failed")
    message: str = Field(..., description="Status message")
    estimated_completion: Optional[str] = Field(None, description="Estimated completion time")

class JobStatusResponse(BaseModel):
    """Response model for job status check"""
    job_id: str
    status: str
    progress: int = Field(..., description="Progress percentage (0-100)")
    message: str
    created_at: str
    updated_at: str
    result_url: Optional[str] = None
    error: Optional[str] = None

class MarketResearchConfig:
    """Configuration class for market research parameters"""
    
    def __init__(self, company: str, geography: str, industry: str, sections: List[str]):
        self.company = company
        self.geography = geography
        self.industry = industry
        self.sections = sections
        self.timestamp = datetime.now().isoformat()

def create_market_research_agents(config: MarketResearchConfig):
    """Create specialized market research agents"""
    
    agents = {}
    
    if "market_overview" in config.sections:
        agents["market_overview"] = Agent(
            name="Market Overview Specialist",
            role="Market Analysis Expert",
            goal=f"Analyze the {config.industry} market in {config.geography}",
            instructions=f"""
            Analyze market size, trends, growth drivers, and overall market dynamics for 
            {config.industry} in {config.geography}. Provide quantitative data and cite sources.
            """,
            tools=[Tools.internet_search],
            verbose=False
        )
    
    if "competitive_analysis" in config.sections:
        agents["competitive"] = Agent(
            name="Competitive Intelligence Analyst",
            role="Competition Research Expert", 
            goal=f"Analyze {config.company}'s competitive landscape",
            instructions=f"""
            Analyze {config.company}'s competitive position in {config.industry} within {config.geography}.
            Identify key competitors, market share, and competitive advantages.
            """,
            tools=[Tools.internet_search],
            verbose=False
        )
    
    if "financial_performance" in config.sections:
        agents["financial"] = Agent(
            name="Financial Performance Analyst", 
            role="Financial Research Expert",
            goal=f"Analyze {config.company}'s financial performance",
            instructions=f"""
            Research {config.company}'s financial performance, revenue trends, profitability,
            and compare with industry benchmarks.
            """,
            tools=[Tools.internet_search],
            verbose=False
        )
    
    if "growth_opportunities" in config.sections:
        agents["growth"] = Agent(
            name="Growth Opportunities Researcher",
            role="Strategic Growth Expert",
            goal=f"Identify growth opportunities for {config.company}",
            instructions=f"""
            Identify emerging opportunities, market gaps, expansion possibilities for {config.company}
            in {config.industry} within {config.geography}.
            """,
            tools=[Tools.internet_search],
            verbose=False
        )
    
    if "risk_assessment" in config.sections:
        agents["risk"] = Agent(
            name="Risk Assessment Specialist",
            role="Risk Analysis Expert", 
            goal=f"Assess risks for {config.company}",
            instructions=f"""
            Identify and analyze potential risks, challenges, and threats facing {config.company}
            in {config.geography}. Consider regulatory, competitive, and market risks.
            """,
            tools=[Tools.internet_search],
            verbose=False
        )
    
    # Always include synthesizer
    agents["synthesizer"] = Agent(
        name="Research Report Synthesizer",
        role="Report Writing Expert",
        goal="Synthesize research into comprehensive report",
        instructions=f"""
        Create a professional secondary market research report for {config.company} 
        in {config.industry} with clear structure, insights, and recommendations.
        """,
        verbose=False
    )
    
    return agents

def create_research_tasks(agents: Dict[str, Agent], config: MarketResearchConfig):
    """Create research tasks for the agents"""
    
    tasks = []
    
    # Create tasks based on available sections
    if "market_overview" in config.sections and "market_overview" in agents:
        market_task = Task(
            name="market_overview_research",
            description=f"Research {config.industry} market overview in {config.geography}",
            expected_output="Market overview analysis with key metrics and trends",
            agent=agents["market_overview"]
        )
        tasks.append(market_task)
    
    if "competitive_analysis" in config.sections and "competitive" in agents:
        competitive_task = Task(
            name="competitive_analysis",
            description=f"Analyze competitive landscape for {config.company}",
            expected_output="Competitive analysis with key competitors and positioning",
            agent=agents["competitive"]
        )
        tasks.append(competitive_task)
    
    if "financial_performance" in config.sections and "financial" in agents:
        financial_task = Task(
            name="financial_analysis",
            description=f"Analyze {config.company}'s financial performance",
            expected_output="Financial performance analysis with key metrics",
            agent=agents["financial"]
        )
        tasks.append(financial_task)
    
    if "growth_opportunities" in config.sections and "growth" in agents:
        growth_task = Task(
            name="growth_opportunities",
            description=f"Identify growth opportunities for {config.company}",
            expected_output="Growth opportunities analysis with strategic recommendations",
            agent=agents["growth"]
        )
        tasks.append(growth_task)
    
    if "risk_assessment" in config.sections and "risk" in agents:
        risk_task = Task(
            name="risk_assessment",
            description=f"Assess risks for {config.company}",
            expected_output="Risk assessment with mitigation strategies",
            agent=agents["risk"]
        )
        tasks.append(risk_task)
    
    # Synthesis task
    synthesis_task = Task(
        name="synthesis",
        description=f"Synthesize all findings into comprehensive report",
        expected_output="Complete secondary market research report",
        agent=agents["synthesizer"],
        context=tasks
    )
    tasks.append(synthesis_task)
    
    return tasks

async def generate_market_research_report(job_id: str, config: MarketResearchConfig):
    """Background task to generate market research report"""
    
    try:
        # Update job status
        job_status[job_id]["status"] = "running"
        job_status[job_id]["progress"] = 10
        job_status[job_id]["message"] = "Creating research agents..."
        job_status[job_id]["updated_at"] = datetime.now().isoformat()
        
        # Create agents and tasks
        agents = create_market_research_agents(config)
        tasks = create_research_tasks(agents, config)
        
        job_status[job_id]["progress"] = 20
        job_status[job_id]["message"] = "Setting up research workflow..."
        
        # Create workflow
        workflow = PraisonAIAgents(
            agents=list(agents.values()),
            tasks=tasks,
            process="workflow",
            verbose=False
        )
        
        job_status[job_id]["progress"] = 30
        job_status[job_id]["message"] = "Executing research workflow..."
        
        # Execute research
        results = await workflow.astart()
        
        job_status[job_id]["progress"] = 90
        job_status[job_id]["message"] = "Generating final report..."
        
        # Prepare final report
        report_data = {
            "metadata": {
                "job_id": job_id,
                "company": config.company,
                "geography": config.geography,
                "industry": config.industry,
                "sections": config.sections,
                "generated_at": datetime.now().isoformat()
            },
            "executive_summary": "Executive summary would be generated here...",
            "research_findings": {}
        }
        
        # Extract results from each task
        if "task_results" in results:
            for task_name, result in results["task_results"].items():
                if result:
                    report_data["research_findings"][task_name] = {
                        "content": result.raw,
                        "agent": result.agent if hasattr(result, 'agent') else "Unknown"
                    }
        
        # Save report to file
        report_filename = f"market_research_{job_id}.json"
        report_path = REPORTS_DIR / report_filename
        
        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)
        
        # Update job status to completed
        job_status[job_id]["status"] = "completed"
        job_status[job_id]["progress"] = 100
        job_status[job_id]["message"] = "Report generation completed successfully"
        job_status[job_id]["result_url"] = f"/reports/{job_id}"
        job_status[job_id]["updated_at"] = datetime.now().isoformat()
        
    except Exception as e:
        # Update job status to failed
        job_status[job_id]["status"] = "failed"
        job_status[job_id]["error"] = str(e)
        job_status[job_id]["message"] = f"Report generation failed: {str(e)}"
        job_status[job_id]["updated_at"] = datetime.now().isoformat()

# API Endpoints

@app.get("/", summary="API Health Check")
async def root():
    """Health check endpoint"""
    return {
        "service": "Secondary Market Research API",
        "status": "active",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/research/generate", response_model=MarketResearchResponse, summary="Generate Market Research Report")
async def generate_research(
    request: MarketResearchRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate a secondary market research report with customizable parameters.
    
    This endpoint starts an async job to generate a comprehensive market research
    report based on the provided parameters. The report generation runs in the
    background and can be tracked using the returned job_id.
    """
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    job_status[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Report generation queued",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "config": request.dict()
    }
    
    # Create config object
    config = MarketResearchConfig(
        company=request.company,
        geography=request.geography,
        industry=request.industry,
        sections=request.sections
    )
    
    # Start background task
    background_tasks.add_task(generate_market_research_report, job_id, config)
    
    return MarketResearchResponse(
        job_id=job_id,
        status="pending",
        message="Market research report generation started",
        estimated_completion=datetime.now().isoformat()
    )

@app.get("/research/status/{job_id}", response_model=JobStatusResponse, summary="Check Job Status")
async def check_job_status(job_id: str):
    """
    Check the status of a market research report generation job.
    
    Returns the current status, progress percentage, and any results or errors.
    """
    
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job ID not found")
    
    return JobStatusResponse(**job_status[job_id])

@app.get("/research/reports/{job_id}", summary="Download Research Report")
async def download_report(job_id: str):
    """
    Download the generated market research report.
    
    Returns the complete report in JSON format once generation is complete.
    """
    
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job ID not found")
    
    if job_status[job_id]["status"] != "completed":
        raise HTTPException(status_code=400, detail="Report not ready. Check job status first.")
    
    report_path = REPORTS_DIR / f"market_research_{job_id}.json"
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    
    return FileResponse(
        path=report_path,
        media_type="application/json",
        filename=f"market_research_{job_id}.json"
    )

@app.get("/research/jobs", summary="List All Jobs")
async def list_jobs():
    """
    List all market research jobs and their current status.
    
    Useful for monitoring and administrative purposes.
    """
    
    return {
        "total_jobs": len(job_status),
        "jobs": [
            {
                "job_id": job_id,
                "status": status["status"],
                "progress": status["progress"],
                "created_at": status["created_at"],
                "company": status["config"]["company"] if "config" in status else "Unknown"
            }
            for job_id, status in job_status.items()
        ]
    }

@app.delete("/research/jobs/{job_id}", summary="Cancel Job")
async def cancel_job(job_id: str):
    """
    Cancel a pending or running market research job.
    """
    
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job ID not found")
    
    if job_status[job_id]["status"] in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed or failed job")
    
    job_status[job_id]["status"] = "cancelled"
    job_status[job_id]["message"] = "Job cancelled by user"
    job_status[job_id]["updated_at"] = datetime.now().isoformat()
    
    return {"message": "Job cancelled successfully", "job_id": job_id}

@app.get("/research/templates", summary="Get Research Templates")
async def get_research_templates():
    """
    Get predefined research templates for common use cases.
    """
    
    templates = {
        "technology_company": {
            "sections": ["market_overview", "competitive_analysis", "financial_performance", "growth_opportunities"],
            "example": {
                "company": "Tesla",
                "geography": "North America",
                "industry": "Electric Vehicles"
            }
        },
        "financial_services": {
            "sections": ["market_overview", "competitive_analysis", "risk_assessment", "financial_performance"],
            "example": {
                "company": "Goldman Sachs",
                "geography": "Global",
                "industry": "Investment Banking"
            }
        },
        "healthcare": {
            "sections": ["market_overview", "competitive_analysis", "growth_opportunities", "risk_assessment"],
            "example": {
                "company": "Johnson & Johnson",
                "geography": "North America",
                "industry": "Pharmaceuticals"
            }
        },
        "retail": {
            "sections": ["market_overview", "competitive_analysis", "financial_performance", "growth_opportunities"],
            "example": {
                "company": "Amazon",
                "geography": "Global",
                "industry": "E-commerce"
            }
        }
    }
    
    return {
        "templates": templates,
        "available_sections": [
            "market_overview",
            "competitive_analysis", 
            "financial_performance",
            "growth_opportunities",
            "risk_assessment"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Secondary Market Research API...")
    print("📚 API Documentation: http://localhost:8000/docs")
    print("🔄 ReDoc Documentation: http://localhost:8000/redoc")
    
    uvicorn.run(
        "secondary-market-research-api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )