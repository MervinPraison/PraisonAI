from praisonaiagents import Agent, Agents, MCP
import gradio as gr

def search_airbnb(query):
    airbnb_agent = Agent(
        instructions=query+" on Airbnb",
        llm="gpt-4o-mini",
        tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt")
    )

    whatsapp_agent = Agent(
        instructions="""Send AirBnb Search Result to 'Mervin Praison'. Don't include Phone Number in Response, but include the AirBnb Search Result""",
        llm="gpt-4o-mini",
        tools=MCP("python /Users/praison/whatsapp-mcp/whatsapp-mcp-server/main.py")
    )

    agents = Agents(agents=[airbnb_agent, whatsapp_agent])

    result = agents.start()
    return f"## Airbnb Search Results\n\n{result}"

demo = gr.Interface(
    fn=search_airbnb,
    inputs=gr.Textbox(placeholder="I want to book an apartment in Paris for 2 nights..."),
    outputs=gr.Markdown(),
    title="WhatsApp MCP Agent",
    description="Enter your booking requirements below:"
)

if __name__ == "__main__":
    demo.launch()