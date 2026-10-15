"""Report the interpreter build and resolved versions of key distributions."""

import json
import platform
import sys
from importlib import metadata

KEY = ["praisonaiagents", "openai", "httpx", "pydantic", "litellm", "langgraph",
       "langchain-openai", "langchain-core", "crewai", "agno", "openai-agents",
       "autogen-agentchat", "autogen-ext", "autogen-core", "aiohttp", "requests"]
versions = {}
for name in KEY:
    try:
        versions[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        pass
print(json.dumps({"python": sys.version.split()[0], "python_build": platform.python_build(),
                  "implementation": platform.python_implementation(),
                  "versions": versions,
                  "distributions": len(list(metadata.distributions()))}))
