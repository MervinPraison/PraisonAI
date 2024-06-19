# Reddit PraisonAI Integration

```
export REDDIT_USER_AGENT=[USER]
export REDDIT_CLIENT_SECRET=xxxxxx
export REDDIT_CLIENT_ID=xxxxxx
```

tools.py

```
from langchain_community.tools.reddit_search.tool import RedditSearchRun
```

agents.yaml

```
framework: crewai
topic: research about the causes of lung disease
roles:
  research_analyst:
    backstory: Experienced in analyzing scientific data related to respiratory health.
    goal: Analyze data on lung diseases
    role: Research Analyst
    tasks:
      data_analysis:
        description: Gather and analyze data on the causes and risk factors of lung
          diseases.
        expected_output: Report detailing key findings on lung disease causes.
    tools:
    - 'RedditSearchRun'
```