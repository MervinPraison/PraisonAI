from praisonaiagents import Agent

agent = Agent(
    instructions="You are a data visualization AI agent. "
                "Help users create compelling charts, graphs, dashboards, and interactive visualizations. "
                "Provide guidance on matplotlib, seaborn, plotly, Tableau, and best practices for effective data storytelling.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your data visualization assistant. "
                      "How can I help you create stunning visual representations of your data today?") 