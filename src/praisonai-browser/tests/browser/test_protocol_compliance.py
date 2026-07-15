"""C11 protocol compliance and optional live LLM tests for praisonai-browser."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src" / "praisonai-agents"))
sys.path.insert(0, str(REPO))


class TestBrowserProtocolCompliance:
    def test_browser_agent_satisfies_protocol(self):
        from praisonaiagents.tools.protocols.browser import BrowserAgentProtocol
        from praisonai_browser.agent import BrowserAgent

        agent = BrowserAgent()
        assert isinstance(agent, BrowserAgentProtocol)

    def test_observation_round_trip(self):
        from praisonaiagents.tools.protocols.browser import BrowserObservation
        from praisonai_browser._protocol_bridge import observation_from_dict, observation_to_dict

        raw = {
            "session_id": "s1",
            "task": "open example.com",
            "url": "https://example.com",
            "title": "Example",
            "elements": [],
            "step_number": 1,
        }
        obs = observation_from_dict(raw)
        assert isinstance(obs, BrowserObservation)
        assert observation_to_dict(obs)["url"] == "https://example.com"

    def test_action_round_trip_submit_and_value(self):
        from praisonai_browser._protocol_bridge import action_from_agent_dict, action_to_agent_dict

        raw = {
            "action": "submit",
            "selector": "#search",
            "value": "praisonai",
            "thought": "submit search",
            "done": False,
        }
        protocol_action = action_from_agent_dict(raw)
        wire = action_to_agent_dict(protocol_action)
        assert wire["action"] == "submit"
        assert wire["value"] == "praisonai"
        assert action_from_agent_dict(wire).action.value == "submit"


@pytest.mark.network
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY required")
class TestBrowserAgentLiveLLM:
    def test_process_observation_real_api(self):
        from praisonai_browser.agent import BrowserAgent

        agent = BrowserAgent(model="gpt-4o-mini", verbose=False)
        observation = {
            "session_id": "live-test",
            "task": "Confirm the page title contains Example",
            "url": "https://example.com",
            "title": "Example Domain",
            "elements": [
                {
                    "selector": "h1",
                    "tag": "h1",
                    "text": "Example Domain",
                    "role": "heading",
                    "interactable": False,
                }
            ],
            "step_number": 0,
        }
        action = agent.process_observation(observation)
        assert action.get("action") in {
            "click", "type", "scroll", "navigate", "wait", "done",
            "submit", "clear_input",
        }
        assert "thought" in action

    def test_process_observation_protocol_real_api(self):
        from praisonaiagents.tools.protocols.browser import BrowserObservation
        from praisonai_browser.agent import BrowserAgent

        agent = BrowserAgent(model="gpt-4o-mini")
        obs = BrowserObservation.from_dict(
            {
                "session_id": "live-proto",
                "task": "Mark done when title is Example Domain",
                "url": "https://example.com",
                "title": "Example Domain",
                "elements": [],
                "step_number": 0,
            }
        )
        action = agent.process_observation_protocol(obs)
        assert action.action.value in {
            "click", "type", "scroll", "navigate", "wait", "done",
            "submit", "clear_input",
        }
