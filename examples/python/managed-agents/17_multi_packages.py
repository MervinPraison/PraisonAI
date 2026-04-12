from praisonai import Agent, ManagedAgent, ManagedConfig

# Multiple package managers — pip + npm installed before agent starts
managed = ManagedAgent(
    config=ManagedConfig(
        name="Full Stack Agent",
        model="claude-haiku-4-5",
        system="You are a full stack developer.",
        packages={
            "pip": ["pandas", "numpy", "scikit-learn"],
            "npm": ["express"],
        },
    ),
)

agent = Agent(name="fullstack", backend=managed)
result = agent.start(
    "Verify pandas and express are installed: run 'python3 -c \"import pandas; print(pandas.__version__)\"' and 'node -e \"console.log(require.resolve('express'))\"'",
    stream=True,
)

print("\nAgent finished.")
