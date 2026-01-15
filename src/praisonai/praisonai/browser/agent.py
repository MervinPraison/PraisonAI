"""Browser Agent — AI agent for browser automation.

Uses PraisonAI agents to decide browser actions based on observations.
"""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("praisonai.browser.agent")


# System prompt for browser automation
BROWSER_AGENT_SYSTEM_PROMPT = """You are a precise browser automation agent. Complete tasks in the FEWEST steps possible.

## Available Actions
- **type**: Type text into INPUT element. Use the EXACT selector from the element list.
- **submit**: Press Enter to submit a form/search. Use after typing in search box.
- **click**: Click BUTTON or LINK. Use the EXACT selector from the element list.
- **scroll**: Scroll page (direction: "up" or "down")
- **navigate**: Go to URL directly (use for known URLs)
- **done**: Task complete - ONLY use when goal is achieved

## Element Types in Observation
Elements are marked with types:
- INPUT → type text here
- BUTTON → click to submit
- LINK → click to navigate to another page

## Multi-Step Tasks
When user says "search X and inside that search Y":
1. Type "X" in the search INPUT
2. Press submit (Enter) to search
3. Click a LINK in results to navigate to that website
4. Then search for "Y" on the new page

DO NOT keep typing in the same search box. Click LINKs to navigate!

## Response Format (JSON only)
```json
{
  "thought": "Brief reasoning (1 sentence)",
  "action": "type|submit|click|scroll|navigate|done",
  "selector": "exact selector from element list",
  "value": "text to type (for type action)",
  "done": false
}
```

CRITICAL: After typing a search query, use "submit" action to press Enter.
"""


class BrowserAgent:
    """Agent that processes browser observations and returns actions.
    
    This is a thin wrapper that creates a PraisonAI agent with browser-specific
    configuration and tools.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_steps: int = 20,
        verbose: bool = False,
    ):
        """Initialize browser agent.
        
        Args:
            model: LLM model to use (e.g., "gpt-4o", "gemini/gemini-2.0-flash")
            max_steps: Maximum steps before stopping
            verbose: Enable verbose logging
        """
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self._agent = None
        self._current_goal: Optional[str] = None
    
    def _ensure_agent(self):
        """Lazily initialize the PraisonAI agent."""
        if self._agent is not None:
            return
        
        try:
            from praisonaiagents import Agent
        except ImportError:
            raise ImportError(
                "praisonaiagents is required. Install it with: pip install praisonaiagents"
            )
        
        self._agent = Agent(
            name="BrowserAgent",
            role="Browser Automation Specialist",
            goal="Help users accomplish tasks by controlling a web browser",
            backstory="You are an expert at navigating websites and performing automated actions.",
            instructions=BROWSER_AGENT_SYSTEM_PROMPT,
            llm=self.model,
        )
    
    def process_observation(
        self,
        observation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process an observation and return the next action.
        
        Args:
            observation: Dict containing:
                - task: The user's goal
                - url: Current page URL
                - title: Page title
                - elements: List of actionable elements
                - screenshot: Base64 screenshot (optional)
                - step_number: Current step
        
        Returns:
            Action dict containing:
                - action: Action type
                - selector: CSS selector (if applicable)
                - text: Text to type (if applicable)
                - thought: Agent's reasoning
                - done: Whether goal is complete
        """
        self._ensure_agent()
        
        # Build observation prompt
        prompt = self._build_prompt(observation)
        
        if self.verbose:
            logger.info(f"Processing observation for step {observation.get('step_number', 0)}")
        
        # Get agent response
        try:
            response = self._agent.chat(prompt)
            action = self._parse_response(response)
        except Exception as e:
            logger.error(f"Agent error: {e}")
            action = {
                "thought": f"Error processing observation: {e}",
                "action": "wait",
                "done": False,
                "error": str(e),
            }
        
        return action
    
    def _build_prompt(self, observation: Dict[str, Any]) -> str:
        """Build prompt from observation with full context."""
        # Start with prominent goal reminder
        original_goal = observation.get('original_goal') or observation.get('task', '')
        parts = [
            "=" * 50,
            f"🎯 ORIGINAL GOAL: {original_goal}",
            "=" * 50,
            "",
            f"**Current URL:** {observation.get('url', '')}",
            f"**Page Title:** {observation.get('title', '')}",
            f"**Step:** {observation.get('step_number', 0)} / {self.max_steps}",
        ]
        
        # Add progress notes if present
        progress = observation.get('progress_notes', '')
        if progress:
            parts.append(f"\n**{progress}**")
        
        # Add action history for context
        action_history = observation.get('action_history', [])
        if action_history:
            parts.append("\n**Recent Actions:**")
            for ah in action_history[-5:]:  # Last 5 actions
                status = "✓" if ah.get('success') else "✗"
                parts.append(f"  {status} {ah.get('action')}: {ah.get('selector', '')[:40]}")
        
        # CRITICAL: Show last action error prominently
        last_error = observation.get('last_action_error')
        if last_error:
            parts.append("\n" + "!" * 50)
            parts.append("⛔ LAST ACTION FAILED!")
            parts.append(f"   Error: {last_error}")
            parts.append("   → You MUST try a DIFFERENT approach!")
            parts.append("   → Do NOT repeat the same action!")
            parts.append("!" * 50)
        
        # Add elements
        elements = observation.get("elements", [])
        if elements:
            parts.append("\n**Actionable Elements:**")
            for i, elem in enumerate(elements[:20]):  # Limit to 20 elements
                selector = elem.get("selector", "")
                text = elem.get("text", "")[:50]  # Truncate
                tag = elem.get("tag", "")
                parts.append(f"  {i+1}. [{tag}] {selector} — \"{text}\"")
        
        # Add error if present
        if observation.get("error"):
            parts.append(f"\n**Error:** {observation['error']}")
        
        # Add self-correction warning
        parts.append("\n" + "=" * 50)
        parts.append("⚠️ CHECK: Does the current page match the ORIGINAL GOAL?")
        parts.append("   If I'm on the wrong page, I should navigate back or start over.")
        parts.append("=" * 50)
        
        parts.append("\nWhat action should I take next? Respond with JSON.")
        
        return "\n".join(parts)
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse agent response into action dict."""
        import json
        import re
        
        # Try to extract JSON from response
        try:
            # Look for JSON in code blocks
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            
            # Try parsing entire response as JSON
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Fallback: extract key fields with regex
        action = {
            "thought": response[:200],
            "action": "wait",
            "done": False,
        }
        
        # Extract action type
        action_match = re.search(r'"action"\s*:\s*"(\w+)"', response)
        if action_match:
            action["action"] = action_match.group(1)
        
        # Extract selector
        selector_match = re.search(r'"selector"\s*:\s*"([^"]+)"', response)
        if selector_match:
            action["selector"] = selector_match.group(1)
        
        # Extract text
        text_match = re.search(r'"text"\s*:\s*"([^"]+)"', response)
        if text_match:
            action["text"] = text_match.group(1)
        
        # Check done
        if '"done": true' in response.lower() or '"done":true' in response.lower():
            action["done"] = True
        
        return action
    
    async def aprocess_observation(
        self,
        observation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Async version of process_observation.
        
        Currently wraps sync version - can be optimized for async agents.
        """
        import asyncio
        return await asyncio.to_thread(self.process_observation, observation)
    
    def reset(self):
        """Reset agent state for new session."""
        self._current_goal = None
        # Note: We don't reset _agent to preserve initialization
