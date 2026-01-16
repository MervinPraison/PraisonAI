"""Tests for browser agent."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from praisonai.browser.agent import BrowserAgent, BROWSER_AGENT_SYSTEM_PROMPT


class TestBrowserAgent:
    """Tests for BrowserAgent class."""
    
    def test_agent_initialization(self):
        """Test agent initialization with defaults."""
        agent = BrowserAgent()
        
        assert agent.model == "gpt-4o-mini"
        assert agent.max_steps == 20
        assert agent.verbose is False
        assert agent._agent is None  # Lazy initialization
    
    def test_agent_custom_model(self):
        """Test agent with custom model."""
        agent = BrowserAgent(model="gpt-4o", max_steps=10, verbose=True)
        
        assert agent.model == "gpt-4o"
        assert agent.max_steps == 10
        assert agent.verbose is True
    
    def test_system_prompt_exists(self):
        """Test that system prompt is defined."""
        assert BROWSER_AGENT_SYSTEM_PROMPT is not None
        assert "browser automation" in BROWSER_AGENT_SYSTEM_PROMPT.lower()
        assert "click" in BROWSER_AGENT_SYSTEM_PROMPT
        assert "type" in BROWSER_AGENT_SYSTEM_PROMPT
    
    def test_build_prompt(self):
        """Test building prompt from observation."""
        agent = BrowserAgent()
        
        observation = {
            "task": "Search for Python tutorials",
            "url": "https://google.com",
            "title": "Google",
            "step_number": 1,
            "elements": [
                {"selector": "#search", "tag": "input", "text": ""},
                {"selector": "#submit", "tag": "button", "text": "Search"},
            ],
        }
        
        prompt = agent._build_prompt(observation)
        
        assert "Search for Python tutorials" in prompt
        assert "https://google.com" in prompt
        assert "Google" in prompt
        assert "#search" in prompt
        assert "#submit" in prompt
    
    def test_build_prompt_with_error(self):
        """Test prompt includes error when present."""
        agent = BrowserAgent()
        
        observation = {
            "task": "Test",
            "url": "https://test.com",
            "title": "Test",
            "step_number": 1,
            "elements": [],
            "error": "Element not found",
        }
        
        prompt = agent._build_prompt(observation)
        
        assert "Element not found" in prompt
        assert "Error" in prompt
    
    def test_build_prompt_limits_elements(self):
        """Test that prompt limits number of elements."""
        agent = BrowserAgent()
        
        # Create 30 elements
        elements = [
            {"selector": f"#elem{i}", "tag": "div", "text": f"Element {i}"}
            for i in range(30)
        ]
        
        observation = {
            "task": "Test",
            "url": "https://test.com",
            "title": "Test",
            "step_number": 1,
            "elements": elements,
        }
        
        prompt = agent._build_prompt(observation)
        
        # Should include only first 20
        assert "#elem0" in prompt
        assert "#elem19" in prompt
        assert "#elem20" not in prompt
    
    def test_parse_response_json(self):
        """Test parsing JSON response."""
        agent = BrowserAgent()
        
        response = '{"action": "click", "selector": "#btn", "thought": "Clicking button", "done": false}'
        action = agent._parse_response(response)
        
        assert action["action"] == "click"
        assert action["selector"] == "#btn"
        assert action["thought"] == "Clicking button"
        assert action["done"] is False
    
    def test_parse_response_json_in_code_block(self):
        """Test parsing JSON in markdown code block."""
        agent = BrowserAgent()
        
        response = '''Let me click the button.
        
```json
{"action": "click", "selector": "#submit", "thought": "Submitting form"}
```

This will submit the form.'''
        
        action = agent._parse_response(response)
        
        assert action["action"] == "click"
        assert action["selector"] == "#submit"
    
    def test_parse_response_done(self):
        """Test parsing done response."""
        agent = BrowserAgent()
        
        response = '{"action": "done", "thought": "Task completed", "done": true}'
        action = agent._parse_response(response)
        
        assert action["done"] is True
        assert action["action"] == "done"
    
    def test_parse_response_fallback(self):
        """Test fallback parsing when JSON is invalid."""
        agent = BrowserAgent()
        
        response = 'I think we should click the button with id "submit"'
        action = agent._parse_response(response)
        
        # Should return a wait action with the response as thought
        assert action["action"] == "wait"
        assert action["done"] is False
    
    def test_parse_response_regex_extraction(self):
        """Test regex-based extraction from malformed JSON."""
        agent = BrowserAgent()
        
        # Malformed but has extractable parts
        response = 'Here is my plan: "action": "click", "selector": "#btn", "done": true'
        action = agent._parse_response(response)
        
        assert action["action"] == "click"
        assert action["selector"] == "#btn"
        assert action["done"] is True
    
    def test_reset_state(self):
        """Test resetting agent state."""
        agent = BrowserAgent()
        agent._current_goal = "Some goal"
        
        agent.reset()
        
        assert agent._current_goal is None


class TestBrowserAgentWithMock:
    """Tests for BrowserAgent with mocked PraisonAI agent."""
    
    @patch("praisonai.browser.agent.BrowserAgent._ensure_agent")
    def test_process_observation(self, mock_ensure):
        """Test processing observation with mocked agent."""
        agent = BrowserAgent()
        
        # Mock the internal agent
        mock_inner_agent = Mock()
        mock_inner_agent.chat.return_value = '{"action": "click", "selector": "#search", "thought": "Clicking search"}'
        agent._agent = mock_inner_agent
        
        observation = {
            "task": "Search for AI",
            "url": "https://google.com",
            "title": "Google",
            "step_number": 1,
            "elements": [{"selector": "#search", "tag": "input", "text": ""}],
        }
        
        action = agent.process_observation(observation)
        
        assert action["action"] == "click"
        assert action["selector"] == "#search"
        mock_inner_agent.chat.assert_called_once()
    
    @patch("praisonai.browser.agent.BrowserAgent._ensure_agent")
    def test_process_observation_error_handling(self, mock_ensure):
        """Test error handling in process_observation."""
        agent = BrowserAgent()
        
        # Mock agent that raises exception
        mock_inner_agent = Mock()
        mock_inner_agent.chat.side_effect = Exception("API error")
        agent._agent = mock_inner_agent
        
        observation = {
            "task": "Test",
            "url": "https://test.com",
            "title": "Test",
            "step_number": 1,
            "elements": [],
        }
        
        action = agent.process_observation(observation)
        
        assert action["action"] == "wait"
        assert "error" in action
        assert action["done"] is False


class TestBrowserAgentAsync:
    """Tests for async methods."""
    
    @pytest.mark.asyncio
    async def test_aprocess_observation(self):
        """Test async observation processing."""
        agent = BrowserAgent()
        
        # Mock the sync method
        with patch.object(agent, "process_observation") as mock_process:
            mock_process.return_value = {"action": "click", "done": False}
            
            observation = {
                "task": "Test",
                "url": "https://test.com",
                "title": "Test",
                "step_number": 1,
                "elements": [],
            }
            
            action = await agent.aprocess_observation(observation)
            
            assert action["action"] == "click"
            mock_process.assert_called_once_with(observation)


class TestConsentDialogHandling:
    """Tests for cookie consent dialog detection and handling."""
    
    def test_build_prompt_with_overlay_info(self):
        """Test that overlay info is included in prompt when detected."""
        agent = BrowserAgent()
        
        observation = {
            "task": "Search for AI on Google",
            "url": "https://google.com",
            "title": "Google",
            "step_number": 1,
            "elements": [
                {"selector": "button.accept", "tag": "button", "text": "Accept all", "type": "consent_button"},
                {"selector": "#search", "tag": "input", "text": ""},
            ],
            "overlay_info": {
                "detected": True,
                "type": "consent_dialog",
                "selector": '[role="dialog"]',
            },
        }
        
        prompt = agent._build_prompt(observation)
        
        # Should contain overlay warning
        assert "COOKIE CONSENT" in prompt or "OVERLAY" in prompt
        assert "consent_dialog" in prompt or "consent" in prompt.lower()
    
    def test_build_prompt_with_action_history(self):
        """Test that action history is included in prompt."""
        agent = BrowserAgent()
        
        observation = {
            "task": "Test",
            "url": "https://test.com",
            "title": "Test",
            "step_number": 3,
            "elements": [],
            "action_history": [
                {"action": "navigate", "selector": "", "success": True},
                {"action": "click", "selector": "#btn", "success": False},
            ],
        }
        
        prompt = agent._build_prompt(observation)
        
        # Should contain action history section
        assert "Recent Actions" in prompt
        assert "navigate" in prompt
        assert "click" in prompt
    
    def test_build_prompt_with_consent_elements_first(self):
        """Test that consent elements are highlighted when present."""
        agent = BrowserAgent()
        
        observation = {
            "task": "Test",
            "url": "https://google.com",
            "title": "Google",
            "step_number": 1,
            "elements": [
                {"selector": "[jsname='abc']", "tag": "button", "text": "Accept all", "type": "consent_button", "isConsentButton": True},
                {"selector": "#search", "tag": "input", "text": "", "type": ""},
            ],
            "overlay_info": {"detected": True, "type": "consent_dialog"},
        }
        
        prompt = agent._build_prompt(observation)
        
        # Should show consent dialog detected prominently
        assert "🚨" in prompt or "COOKIE" in prompt or "CONSENT" in prompt
    
    def test_system_prompt_contains_consent_instructions(self):
        """Test that system prompt includes consent handling instructions."""
        assert "consent" in BROWSER_AGENT_SYSTEM_PROMPT.lower() or "cookie" in BROWSER_AGENT_SYSTEM_PROMPT.lower()
        assert "Accept" in BROWSER_AGENT_SYSTEM_PROMPT or "accept" in BROWSER_AGENT_SYSTEM_PROMPT.lower()
        assert "overlay" in BROWSER_AGENT_SYSTEM_PROMPT.lower() or "dialog" in BROWSER_AGENT_SYSTEM_PROMPT.lower()
    
    def test_build_prompt_with_last_action_error(self):
        """Test that last action error is shown prominently."""
        agent = BrowserAgent()
        
        observation = {
            "task": "Test",
            "url": "https://test.com",
            "title": "Test",
            "step_number": 2,
            "elements": [],
            "last_action_error": "Element not found: #missing-button",
        }
        
        prompt = agent._build_prompt(observation)
        
        # Should contain the error prominently
        assert "Element not found" in prompt or "FAILED" in prompt

