"""Watch a flow run, step by step: click Run and each step lights up on the map.

No API key needed (the steps are plain Python that take a moment each).

    pip install "praisonai[ui]"
    python watch_flow.py          # opens http://127.0.0.1:8090/

Map: dashed = not reached, blue = running now, green = done.
After a run, press Play to go through it again one step at a time.
"""

import time

from praisonaiagents import AgentFlow
from praisonaiagents.workflows import StepResult
from praisonai.replay import watch


def research(ctx):
    time.sleep(1.5)
    return StepResult(output=f"3 sources about {ctx.input}")


def outline(ctx):
    time.sleep(1.5)
    return StepResult(output="intro, body, close")


def draft(ctx):
    time.sleep(1.5)
    return StepResult(output="first draft")


def review(ctx):
    time.sleep(1.5)
    return StepResult(output="approved")


flow = AgentFlow(name="Write an article", steps=[research, outline, draft, review])
watch(flow, input="solar sails")
