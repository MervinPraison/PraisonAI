"""
Secondary Market Research Agent System

This system creates a comprehensive market research solution with customizable 
inputs for company, geography, and industry sections. It generates detailed 
reports suitable for secondary market research.

Features:
- Multi-agent system with specialized research roles
- Customizable geography and company focus
- Structured report generation
- Market analysis and competitive intelligence
- FastAPI integration ready
"""

from praisonaiagents import Agent, Task, PraisonAIAgents, Tools
from typing import Dict, List, Any, Optional
import asyncio
import json
from datetime import datetime

class MarketResearchConfig:
    """Configuration class for market research parameters"""
    
    def __init__(self, 
                 company: str = "Tesla", 
                 geography: str = "North America",
                 industry: str = "Electric Vehicles",
                 sections: List[str] = None):
        self.company = company
        self.geography = geography
        self.industry = industry
        self.sections = sections or [
            "market_overview",
            "competitive_analysis", 
            "financial_performance",
            "growth_opportunities",
            "risk_assessment"
        ]
        self.timestamp = datetime.now().isoformat()

def create_market_research_agents(config: MarketResearchConfig):
    """Create specialized market research agents"""
    
    # Market Overview Agent
    market_overview_agent = Agent(
        name="Market Overview Specialist",
        role="Market Analysis Expert",
        goal=f"Analyze the {config.industry} market in {config.geography}",
        instructions=f"""
        You are a market research specialist focused on {config.industry} in {config.geography}.
        Analyze market size, trends, growth drivers, and overall market dynamics.
        Focus on current market conditions and future projections.
        Provide quantitative data where possible and cite reliable sources.
        """,
        tools=[Tools.internet_search],
        verbose=True
    )
    
    # Competitive Intelligence Agent  
    competitive_agent = Agent(
        name="Competitive Intelligence Analyst",
        role="Competition Research Expert", 
        goal=f"Analyze {config.company}'s competitive landscape",
        instructions=f"""
        You are a competitive intelligence specialist analyzing {config.company}'s position
        in the {config.industry} market within {config.geography}.
        Identify key competitors, market share, competitive advantages, and positioning.
        Analyze competitor strategies, strengths, weaknesses, and market positioning.
        """,
        tools=[Tools.internet_search],
        verbose=True
    )
    
    # Financial Performance Agent
    financial_agent = Agent(
        name="Financial Performance Analyst", 
        role="Financial Research Expert",
        goal=f"Analyze {config.company}'s financial performance and metrics",
        instructions=f"""
        You are a financial analyst specializing in {config.industry} companies.
        Research {config.company}'s financial performance, revenue trends, profitability,
        key financial metrics, and compare with industry benchmarks.
        Focus on recent financial data and performance indicators.
        """,
        tools=[Tools.internet_search],
        verbose=True
    )
    
    # Growth Opportunities Agent
    growth_agent = Agent(
        name="Growth Opportunities Researcher",
        role="Strategic Growth Expert",
        goal=f"Identify growth opportunities for {config.company}",
        instructions=f"""
        You are a strategic growth analyst focusing on {config.industry} in {config.geography}.
        Identify emerging opportunities, market gaps, expansion possibilities,
        new product/service opportunities, and strategic growth vectors for {config.company}.
        Consider technological trends, regulatory changes, and market evolution.
        """,
        tools=[Tools.internet_search],
        verbose=True
    )
    
    # Risk Assessment Agent
    risk_agent = Agent(
        name="Risk Assessment Specialist",
        role="Risk Analysis Expert", 
        goal=f"Assess risks and challenges for {config.company}",
        instructions=f"""
        You are a risk assessment specialist for {config.industry} companies.
        Identify and analyze potential risks, challenges, and threats facing {config.company}
        in {config.geography}. Consider regulatory, competitive, technological, 
        economic, and operational risks.
        """,
        tools=[Tools.internet_search],
        verbose=True
    )
    
    # Report Synthesizer Agent
    synthesizer_agent = Agent(
        name="Research Report Synthesizer",
        role="Report Writing Expert",
        goal="Synthesize research into comprehensive market research report",
        instructions=f"""
        You are an expert report writer specializing in market research reports.
        Synthesize all research findings into a comprehensive, well-structured 
        secondary market research report for {config.company} in {config.industry}.
        
        Create a professional report with:
        - Executive Summary
        - Market Overview 
        - Competitive Analysis
        - Financial Performance Analysis
        - Growth Opportunities
        - Risk Assessment
        - Conclusions and Recommendations
        
        Use clear headings, bullet points, and structured formatting.
        Include key insights and actionable recommendations.
        """,
        verbose=True
    )
    
    return {
        "market_overview": market_overview_agent,
        "competitive": competitive_agent, 
        "financial": financial_agent,
        "growth": growth_agent,
        "risk": risk_agent,
        "synthesizer": synthesizer_agent
    }

def create_research_tasks(agents: Dict[str, Agent], config: MarketResearchConfig):
    """Create research tasks for the agents"""
    
    tasks = []
    
    # Market Overview Task
    if "market_overview" in config.sections:
        market_task = Task(
            name="market_overview_research",
            description=f"""
            Conduct comprehensive market overview research for {config.industry} 
            in {config.geography}. Include:
            - Market size and valuation
            - Growth trends and projections  
            - Key market drivers
            - Market segments
            - Regulatory environment
            """,
            expected_output="Detailed market overview analysis with quantitative data",
            agent=agents["market_overview"],
            is_start=True,
            next_tasks=["competitive_analysis"] if "competitive_analysis" in config.sections else ["synthesis"]
        )
        tasks.append(market_task)
    
    # Competitive Analysis Task  
    if "competitive_analysis" in config.sections:
        competitive_task = Task(
            name="competitive_analysis",
            description=f"""
            Analyze competitive landscape for {config.company} in {config.industry}:
            - Identify top 5-7 competitors
            - Market share analysis
            - Competitive positioning
            - Competitor strengths and weaknesses
            - Competitive strategies
            """,
            expected_output="Comprehensive competitive intelligence report",
            agent=agents["competitive"],
            next_tasks=["financial_analysis"] if "financial_performance" in config.sections else ["synthesis"]
        )
        tasks.append(competitive_task)
    
    # Financial Performance Task
    if "financial_performance" in config.sections:
        financial_task = Task(
            name="financial_analysis", 
            description=f"""
            Analyze {config.company}'s financial performance:
            - Revenue trends (last 3-5 years)
            - Profitability metrics
            - Key financial ratios
            - Industry benchmark comparison
            - Financial health assessment
            """,
            expected_output="Detailed financial performance analysis",
            agent=agents["financial"],
            next_tasks=["growth_opportunities"] if "growth_opportunities" in config.sections else ["synthesis"]
        )
        tasks.append(financial_task)
    
    # Growth Opportunities Task
    if "growth_opportunities" in config.sections:
        growth_task = Task(
            name="growth_opportunities",
            description=f"""
            Identify growth opportunities for {config.company}:
            - Market expansion opportunities
            - New product/service opportunities  
            - Strategic partnerships potential
            - Technology advancement opportunities
            - Emerging market trends
            """,
            expected_output="Strategic growth opportunities analysis",
            agent=agents["growth"],
            next_tasks=["risk_assessment"] if "risk_assessment" in config.sections else ["synthesis"]
        )
        tasks.append(growth_task)
    
    # Risk Assessment Task
    if "risk_assessment" in config.sections:
        risk_task = Task(
            name="risk_assessment",
            description=f"""
            Assess risks and challenges for {config.company}:
            - Competitive threats
            - Regulatory risks
            - Market risks
            - Operational challenges
            - Technology disruption risks
            """,
            expected_output="Comprehensive risk assessment report",
            agent=agents["risk"],
            next_tasks=["synthesis"]
        )
        tasks.append(risk_task)
    
    # Synthesis Task
    synthesis_task = Task(
        name="synthesis",
        description=f"""
        Synthesize all research findings into a comprehensive secondary market 
        research report for {config.company} in {config.industry} ({config.geography}).
        
        Create a professional report with clear sections, insights, and recommendations.
        Focus on actionable intelligence for business decision-making.
        """,
        expected_output="Complete secondary market research report",
        agent=agents["synthesizer"],
        context=tasks  # Use all previous tasks as context
    )
    tasks.append(synthesis_task)
    
    return tasks

async def run_market_research(config: MarketResearchConfig) -> Dict[str, Any]:
    """Run the complete market research workflow"""
    
    print(f"\n🔍 Starting Secondary Market Research for {config.company}")
    print(f"📍 Geography: {config.geography}")
    print(f"🏭 Industry: {config.industry}")
    print(f"📊 Sections: {', '.join(config.sections)}")
    print("=" * 60)
    
    # Create agents and tasks
    agents = create_market_research_agents(config)
    tasks = create_research_tasks(agents, config)
    
    # Create workflow
    workflow = PraisonAIAgents(
        agents=list(agents.values()),
        tasks=tasks,
        process="workflow",
        verbose=True
    )
    
    # Execute research
    results = await workflow.astart()
    
    return {
        "config": config.__dict__,
        "results": results,
        "timestamp": datetime.now().isoformat()
    }

# Example usage
async def main():
    """Main function demonstrating the market research system"""
    
    # Example 1: Tesla Electric Vehicle Research
    tesla_config = MarketResearchConfig(
        company="Tesla",
        geography="North America", 
        industry="Electric Vehicles",
        sections=["market_overview", "competitive_analysis", "financial_performance", "growth_opportunities"]
    )
    
    tesla_results = await run_market_research(tesla_config)
    
    print("\n📋 Research Complete!")
    print("=" * 60)
    
    # Display results
    if "task_results" in tesla_results["results"]:
        for task_name, result in tesla_results["results"]["task_results"].items():
            if result:
                print(f"\n📌 {task_name.upper()}")
                print("-" * 40) 
                print(result.raw[:500] + "..." if len(result.raw) > 500 else result.raw)
    
    return tesla_results

if __name__ == "__main__":
    # Run the market research
    results = asyncio.run(main())
    
    # Save results to file
    with open("market_research_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to market_research_results.json")