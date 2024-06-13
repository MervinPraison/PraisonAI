## Include praisonai package in your project

Note: Please create agents.yaml file before hand. 

```python
from praisonai import PraisonAI

def basic(): # Basic Mode
    praison_ai = PraisonAI(agent_file="agents.yaml")
    praison_ai.main()

if __name__ == "__main__":
    basic()
```

## All in one

```python
from praisonai import PraisonAI

def basic(): # Basic Mode
    praison_ai = PraisonAI(agent_file="agents.yaml")
    praison_ai.main()
    
def advanced(): # Advanced Mode with options
    praison_ai = PraisonAI(
        agent_file="agents.yaml",
        framework="autogen",
    )
    praison_ai.main()
    
def auto(): # Full Automatic Mode
    praison_ai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praison_ai.framework)
    praison_ai.main()

if __name__ == "__main__":
    basic()
    advanced()
    auto()
```

