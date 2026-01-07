"""
External Sources RAG: Beyond Vector Search

This example demonstrates RAG with external knowledge sources like
web search, APIs, and databases.

RAG Concept: RAG isn't limited to pre-indexed documents. External sources
provide real-time, up-to-date information that complements static knowledge.
"""

from praisonaiagents import Agent

# Simulated external data sources
def mock_web_search(query: str) -> list:
    """Simulate web search results."""
    # In production, this would call a real search API
    mock_results = {
        "weather": [
            {"title": "Current Weather", "snippet": "Today's forecast: Partly cloudy, high of 72°F (22°C), low of 58°F (14°C). Humidity at 45%."},
            {"title": "Weekly Outlook", "snippet": "Rain expected Wednesday and Thursday. Weekend looks sunny with temperatures in the mid-70s."}
        ],
        "news": [
            {"title": "Tech Industry Update", "snippet": "Major tech companies report strong Q3 earnings. AI investments continue to grow across sectors."},
            {"title": "Market Summary", "snippet": "Stock markets closed higher today. S&P 500 up 0.8%, Nasdaq up 1.2%."}
        ],
        "default": [
            {"title": "General Information", "snippet": "Search results would appear here with relevant web content."}
        ]
    }
    
    for key in mock_results:
        if key in query.lower():
            return mock_results[key]
    return mock_results["default"]


def mock_database_query(query: str) -> dict:
    """Simulate database query results."""
    # In production, this would query a real database
    mock_data = {
        "user_stats": {
            "total_users": 15420,
            "active_today": 3250,
            "new_signups": 127,
            "retention_rate": "78%"
        },
        "sales_data": {
            "monthly_revenue": "$1.2M",
            "top_product": "Enterprise Plan",
            "growth_rate": "15% MoM",
            "avg_deal_size": "$4,500"
        },
        "system_health": {
            "uptime": "99.97%",
            "avg_response_time": "145ms",
            "error_rate": "0.02%",
            "active_servers": 24
        }
    }
    
    for key in mock_data:
        if key.replace("_", " ") in query.lower() or key in query.lower():
            return mock_data[key]
    return {"message": "No matching data found"}


def mock_api_call(endpoint: str) -> dict:
    """Simulate API call results."""
    # In production, this would call a real API
    mock_responses = {
        "stock_price": {"symbol": "ACME", "price": 142.50, "change": "+2.3%"},
        "exchange_rate": {"from": "USD", "to": "EUR", "rate": 0.92},
        "crypto": {"bitcoin": "$67,500", "ethereum": "$3,450"}
    }
    
    for key in mock_responses:
        if key in endpoint.lower():
            return mock_responses[key]
    return {"status": "endpoint not found"}


# Static knowledge base for hybrid approach
COMPANY_KNOWLEDGE = [
    {
        "id": "company_overview",
        "content": """
        Acme Corporation is a technology company founded in 2015.
        Headquarters: San Francisco, CA
        Products: Enterprise software, cloud services, AI solutions
        Mission: Empowering businesses through intelligent automation
        """
    },
    {
        "id": "product_info",
        "content": """
        Acme Products:
        - Acme Cloud: Infrastructure-as-a-service platform
        - Acme AI: Machine learning toolkit for enterprises
        - Acme Connect: Integration and API management
        Pricing: Starter ($99/mo), Professional ($499/mo), Enterprise (custom)
        """
    }
]


def web_augmented_rag():
    """Demonstrate RAG augmented with web search."""
    
    print("=" * 60)
    print("WEB-AUGMENTED RAG")
    print("=" * 60)
    
    # Create agent that can use web search
    agent = Agent(
        name="Research Assistant",
        instructions="""You are a research assistant that combines internal knowledge
        with web search results. When answering:
        1. Check if the question requires current/real-time information
        2. Use web search for news, weather, current events
        3. Combine web results with your knowledge for comprehensive answers
        4. Clearly indicate when information comes from web search.""",
        knowledge=COMPANY_KNOWLEDGE,
        user_id="web_demo"
    )
    
    # Simulate web-augmented queries
    queries = [
        ("What's the weather like today?", True),  # Needs web
        ("Tell me about Acme Corporation's products", False),  # Static knowledge
        ("What's happening in the tech industry?", True),  # Needs web
    ]
    
    for query, needs_web in queries:
        print(f"\n📝 Query: {query}")
        
        if needs_web:
            # Augment with web search
            web_results = mock_web_search(query)
            web_context = "\n".join([f"- {r['title']}: {r['snippet']}" for r in web_results])
            augmented_query = f"{query}\n\nWeb search results:\n{web_context}"
            response = agent.chat(augmented_query)
            print("🌐 (Web-augmented)")
        else:
            response = agent.chat(query)
            print("📚 (Static knowledge)")
        
        print(f"💡 Answer: {response[:250]}..." if len(str(response)) > 250 else f"💡 Answer: {response}")
        print("-" * 40)


def database_augmented_rag():
    """Demonstrate RAG augmented with database queries."""
    
    print("\n" + "=" * 60)
    print("DATABASE-AUGMENTED RAG")
    print("=" * 60)
    
    agent = Agent(
        name="Business Analyst",
        instructions="""You are a business analyst with access to company databases.
        Interpret data accurately and provide actionable insights.
        When presenting numbers, add context and trends.""",
        knowledge=COMPANY_KNOWLEDGE,
        user_id="db_demo"
    )
    
    queries = [
        "How are our user stats looking?",
        "Give me a sales summary",
        "What's our system health status?"
    ]
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        
        # Fetch database data
        db_data = mock_database_query(query)
        db_context = f"Database results: {db_data}"
        
        augmented_query = f"{query}\n\n{db_context}"
        response = agent.chat(augmented_query)
        
        print(f"🗄️ DB Data: {db_data}")
        print(f"💡 Analysis: {response[:200]}..." if len(str(response)) > 200 else f"💡 Analysis: {response}")
        print("-" * 40)


def api_augmented_rag():
    """Demonstrate RAG augmented with API calls."""
    
    print("\n" + "=" * 60)
    print("API-AUGMENTED RAG")
    print("=" * 60)
    
    agent = Agent(
        name="Financial Assistant",
        instructions="""You are a financial assistant with access to market APIs.
        Provide accurate financial information and context.
        Always note that prices are subject to change.""",
        user_id="api_demo"
    )
    
    queries = [
        ("What's the ACME stock price?", "stock_price"),
        ("USD to EUR exchange rate?", "exchange_rate"),
        ("Crypto market update?", "crypto")
    ]
    
    for query, endpoint in queries:
        print(f"\n📝 Query: {query}")
        
        # Fetch API data
        api_data = mock_api_call(endpoint)
        api_context = f"API response: {api_data}"
        
        augmented_query = f"{query}\n\n{api_context}"
        response = agent.chat(augmented_query)
        
        print(f"🔌 API Data: {api_data}")
        print(f"💡 Response: {response[:200]}..." if len(str(response)) > 200 else f"💡 Response: {response}")
        print("-" * 40)


def hybrid_source_rag():
    """Combine multiple external sources."""
    
    print("\n" + "=" * 60)
    print("HYBRID SOURCE RAG")
    print("=" * 60)
    
    agent = Agent(
        name="Executive Assistant",
        instructions="""You are an executive assistant with access to multiple data sources.
        Synthesize information from static knowledge, databases, and APIs.
        Provide comprehensive briefings that combine all relevant data.""",
        knowledge=COMPANY_KNOWLEDGE,
        user_id="hybrid_demo"
    )
    
    query = "Give me a complete business briefing for today"
    
    # Gather from multiple sources
    db_stats = mock_database_query("user_stats")
    db_sales = mock_database_query("sales_data")
    db_health = mock_database_query("system_health")
    api_stock = mock_api_call("stock_price")
    web_news = mock_web_search("news")
    
    combined_context = f"""
    User Statistics: {db_stats}
    Sales Data: {db_sales}
    System Health: {db_health}
    Stock Price: {api_stock}
    Industry News: {[r['snippet'] for r in web_news]}
    """
    
    augmented_query = f"{query}\n\nData from multiple sources:\n{combined_context}"
    
    print(f"\n📝 Query: {query}")
    print("\n📊 Data Sources:")
    print("   - Database: user_stats, sales_data, system_health")
    print("   - API: stock_price")
    print("   - Web: news search")
    
    response = agent.chat(augmented_query)
    print(f"\n💡 Executive Briefing:\n{response}")


def external_source_patterns():
    """Explain external source patterns."""
    
    print("\n" + "=" * 60)
    print("EXTERNAL SOURCE PATTERNS")
    print("=" * 60)
    
    print("""
    🌐 External Source Integration Patterns:
    
    1. **Query-Time Augmentation**
       - Fetch external data when query arrives
       - Inject into prompt as additional context
       - Best for: Real-time data needs
    
    2. **Scheduled Refresh**
       - Periodically update knowledge base from external sources
       - Index external data for faster retrieval
       - Best for: Semi-static external data
    
    3. **Tool-Based Retrieval**
       - Give agent tools to fetch external data
       - Agent decides when to use external sources
       - Best for: Complex, multi-step queries
    
    4. **Hybrid Static + Dynamic**
       - Combine indexed knowledge with real-time fetches
       - Use static for stable info, dynamic for current
       - Best for: Comprehensive answers
    
    Implementation Example:
    ```python
    def web_search_tool(query: str) -> str:
        # Call search API
        results = search_api.search(query)
        return format_results(results)
    
    agent = Agent(
        knowledge=static_docs,
        tools=[web_search_tool],
        instructions="Use web search for current events..."
    )
    ```
    """)


def main():
    """Run all external source RAG examples."""
    print("\n🚀 PraisonAI External Sources RAG Examples\n")
    
    # Example 1: Web-augmented RAG
    web_augmented_rag()
    
    # Example 2: Database-augmented RAG
    database_augmented_rag()
    
    # Example 3: API-augmented RAG
    api_augmented_rag()
    
    # Example 4: Hybrid sources
    hybrid_source_rag()
    
    # Example 5: Patterns
    external_source_patterns()
    
    print("\n✅ External sources RAG examples completed!")


if __name__ == "__main__":
    main()
