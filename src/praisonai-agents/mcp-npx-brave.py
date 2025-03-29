from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You are a helpful assistant that can search the web for information.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP(
        command="npx",
        args=[
            "-y", 
            "@smithery/cli@latest", 
            "install", 
            "@smithery-ai/brave-search", 
            "--client", 
            "claude", 
            "--config", 
            '{"braveApiKey":"BSANfDaqLKO9wq7e08mrPth9ZlJvKtc"}'
        ],
        timeout=30,  # 3 minutes for brave-search
        debug=True    # Enable detailed logging
    )
)

search_agent.start("Search more information about Praison AI")