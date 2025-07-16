from praisonaiagents import Agent

agent = Agent(
    instructions="You are an AI teaching agent. "
                 "Help users with educational content creation, lesson planning, "
                 "and personalized learning experiences across various subjects.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need to create a lesson plan for teaching Python programming to beginners. "
    "Can you help me design an engaging curriculum?"
) 