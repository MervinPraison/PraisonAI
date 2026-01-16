"""Browser Agent — AI agent for browser automation.

Uses PraisonAI agents to decide browser actions based on observations.
"""

import logging
from typing import Optional, Dict, Any, List, Literal

logger = logging.getLogger("praisonai.browser.agent")


# Pydantic model for structured browser action response
# Lazy import to avoid import-time overhead
def _get_browser_action_model():
    """Lazily create BrowserAction Pydantic model."""
    try:
        from pydantic import BaseModel, Field
    except ImportError:
        return None
    
    class BrowserAction(BaseModel):
        """Structured response for browser automation actions."""
        thought: str = Field(description="Brief reasoning for this action")
        action: Literal["type", "submit", "click", "scroll", "navigate", "done", "wait"] = Field(
            description="Action to perform"
        )
        selector: Optional[str] = Field(None, description="CSS selector for target element")
        value: Optional[str] = Field(None, description="Text value for type action")
        url: Optional[str] = Field(None, description="URL for navigate action")
        direction: Optional[str] = Field(None, description="Scroll direction: up or down")
        done: bool = Field(False, description="Whether the task is complete")
        summary: Optional[str] = Field(
            None, 
            description="Summary of what was accomplished (required when done=true)"
        )
    
    return BrowserAction


# Cache the model after first creation
_browser_action_model = None

def get_browser_action_model():
    """Get the BrowserAction model, creating it lazily if needed."""
    global _browser_action_model
    if _browser_action_model is None:
        _browser_action_model = _get_browser_action_model()
    return _browser_action_model


# Action name normalization - LLM often returns freeform text instead of exact action names
ACTION_MAPPING = {
    # Valid actions (identity)
    "type": "type",
    "submit": "submit", 
    "click": "click",
    "scroll": "scroll",
    "navigate": "navigate",
    "done": "done",
    "wait": "wait",
    "input": "type",
    
    # Common LLM variations -> normalized
    "enter text": "type",
    "enter text and submit": "type",
    "enter": "type",
    "fill": "type",
    "write": "type",
    "text": "type",
    
    "press enter": "submit",
    "submit search": "submit",
    "hit enter": "submit",
    "search": "submit",
    
    "click button": "click",
    "click link": "click",
    "press button": "click",
    "tap": "click",
    "select": "click",
    "press": "click",
    
    "scroll down": "scroll",
    "scroll up": "scroll",
    
    "go to": "navigate",
    "open": "navigate",
    "visit": "navigate",
    "goto": "navigate",
    
    "complete": "done",
    "finish": "done",
    "goal achieved": "done",
    "task complete": "done",
}


def normalize_action(action_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize action name to valid CDP action type.
    
    LLMs often return freeform action descriptions like 'enter text and submit'
    instead of exact action types like 'type'. This normalizes them.
    """
    if not action_dict or "action" not in action_dict:
        action_dict["action"] = "wait"
        return action_dict
    
    raw_action = str(action_dict.get("action", "")).lower().strip()
    
    # Direct match
    if raw_action in ACTION_MAPPING:
        action_dict["action"] = ACTION_MAPPING[raw_action]
        return action_dict
    
    # Fuzzy match - check if any pattern is contained in the action
    for pattern, normalized in ACTION_MAPPING.items():
        if pattern in raw_action:
            action_dict["action"] = normalized
            logger.debug(f"Normalized action '{raw_action}' -> '{normalized}'")
            return action_dict
    
    # Unknown action - log warning and default to wait
    logger.warning(f"Unknown action: '{raw_action}', defaulting to 'wait'")
    action_dict["action"] = "wait"
    return action_dict

# System prompt for browser automation
BROWSER_AGENT_SYSTEM_PROMPT = """You are a precise browser automation agent. Complete ALL parts of multi-step tasks.

## Available Actions
- **type**: Type text into INPUT element. Use the EXACT selector from the element list.
- **submit**: Press Enter to submit a form/search. Use after typing in search box.
- **click**: Click BUTTON or LINK. Use the EXACT selector from the element list.
- **scroll**: Scroll page (direction: "up" or "down")
- **navigate**: Go to URL directly (use for known URLs)
- **done**: Task complete - use ONLY when ALL parts of the goal are achieved

## CRITICAL: Cookie Consent / Overlay Dialogs

⚠️ **IMPORTANT**: If you see elements marked as `consent_button` or with text like "Accept all", "Reject all", "I agree", or similar - you MUST click them FIRST before doing anything else!

These dialogs block all other interactions. Look for:
- Buttons with text containing: "Accept", "Reject", "Agree", "Consent", "OK", "Got it"
- Elements with type="consent_button" in the element list
- Elements at the TOP of the list (consent buttons are prioritized)

**If overlay_info shows detected=true**, you are seeing a consent dialog. Click a consent button immediately!

## CRITICAL: Valid Selector Format
You MUST use valid CSS selectors from the element list. 
NEVER use jQuery-style selectors! These are INVALID:
- ❌ a:contains('text') - NOT VALID CSS
- ❌ $(selector) - NOT VALID CSS
- ❌ :has() - NOT VALID CSS

Use ONLY selectors provided in the element list, such as:
- ✅ #id
- ✅ .classname
- ✅ input[name="value"]
- ✅ button[type="submit"]
- ✅ a[href*="domain.com"]

## CRITICAL: Multi-Step Goals - DO NOT MARK DONE EARLY!

⚠️ **IMPORTANT**: If the goal contains multiple parts separated by commas or "and", you MUST complete ALL parts before marking done!

### Example Multi-Step Goals:
- "go to google, search for AI, click the first link" = 3 STEPS REQUIRED:
  1. Navigate to google.com
  2. Type "AI" and submit search
  3. Click first search result link
  → Only mark done AFTER clicking the link!

- "search for Python and click Wikipedia" = 2 STEPS REQUIRED:
  1. Search for Python
  2. Click Wikipedia link in results
  → Only mark done AFTER clicking Wikipedia!

### How to Parse Goals:
1. Split goal by commas and "and"
2. Count the number of distinct actions
3. Track which actions you've completed
4. Only mark done when ALL actions are complete

## CRITICAL: When to Use "done"

Set "done": true ONLY when ALL of these are true:
- **Every part of the goal is complete** - not just the first part!
- **You can see evidence** that the final action succeeded
- **The URL/page reflects** the final state requested

### Examples:
- Goal "go to google" → DONE when URL shows `google.com`
- Goal "search AI on google" → DONE when URL shows `/search?q=AI`
- Goal "go to google, search AI, click first link" → DONE when you're on a NEW page after clicking a search result (NOT on google.com/search)

⚠️ DO NOT mark done after just navigating if the goal includes searching!
⚠️ DO NOT mark done after just searching if the goal includes clicking!

## Element Types in Observation
- INPUT/TEXTAREA → type text here
- BUTTON → click to submit
- LINK (a) → click to navigate to another page
- consent_button → CLICK FIRST to dismiss blocking dialog

## Response Format (JSON only)
```json
{
  "thought": "Brief reasoning - what part of the goal am I working on?",
  "action": "type|submit|click|scroll|navigate|done",
  "selector": "exact selector from element list",
  "value": "text to type (for type action)",
  "done": true or false,
  "summary": "What was accomplished (REQUIRED when done=true)"
}
```

When task is complete, always include a summary of ALL steps you did, e.g.:
- "Navigated to Google, searched for 'AI', and clicked the first result"
- "Searched for 'Python' and clicked the Wikipedia link"

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
        session_id: Optional[str] = None,
    ):
        """Initialize browser agent.
        
        Args:
            model: LLM model to use (e.g., "gpt-4o", "gemini/gemini-2.0-flash")
            max_steps: Maximum steps before stopping
            verbose: Enable verbose logging
            session_id: Session ID for Agent memory isolation
        """
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self.session_id = session_id
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
            memory=False,  # Disabled: Each step is a fresh LLM call - prevents token explosion
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
                - summary: What was accomplished (when done=true)
        """
        self._ensure_agent()
        
        # Build observation prompt
        prompt = self._build_prompt(observation)
        
        if self.verbose:
            logger.info(f"Processing observation for step {observation.get('step_number', 0)}")
        
        # Check if we have a screenshot for vision-based decision making
        screenshot_base64 = observation.get('screenshot')
        use_vision = screenshot_base64 and 'gpt' in self.model.lower()
        
        # Get agent response with structured output if available
        try:
            action_model = get_browser_action_model()
            
            if use_vision:
                # Use LiteLLM directly for vision-enabled call
                from litellm import completion
                
                if self.verbose:
                    logger.info(f"[VISION] Using screenshot for decision making")
                
                messages = [
                    {"role": "system", "content": BROWSER_AGENT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}
                            },
                        ],
                    }
                ]
                
                response = completion(
                    model=self.model,
                    messages=messages,
                    max_tokens=500,
                )
                
                response_text = response.choices[0].message.content.strip()
                action = self._parse_response(response_text)
                
            elif action_model is not None:
                # Use Pydantic model for guaranteed structured output
                response = self._agent.chat(prompt, output_pydantic=action_model)
                
                # If response is already a dict (parsed by Agent), use it
                if isinstance(response, dict):
                    action = response
                elif hasattr(response, 'model_dump'):
                    # Pydantic v2
                    action = response.model_dump()
                elif hasattr(response, 'dict'):
                    # Pydantic v1
                    action = response.dict()
                else:
                    # String response - needs parsing
                    action = self._parse_response(str(response))
            else:
                # Fallback to string parsing
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
        
        # Normalize action name to valid CDP action type
        # LLMs often return freeform text like "enter text and submit" instead of "type"
        action = normalize_action(action)
        
        return action
    
    def _build_prompt(self, observation: Dict[str, Any]) -> str:
        """Build prompt from observation with full context."""
        # Start with prominent goal reminder
        original_goal = observation.get('original_goal') or observation.get('task', '')
        
        # Parse multi-step goal into parts
        goal_parts = []
        if original_goal:
            # Split by comma and "and" to identify sub-goals
            import re
            # Split by comma or " and " but keep track
            raw_parts = re.split(r',\s*|\s+and\s+', original_goal.lower())
            goal_parts = [p.strip() for p in raw_parts if p.strip()]
        
        parts = [
            "=" * 50,
            f"🎯 ORIGINAL GOAL: {original_goal}",
        ]
        
        # Show goal breakdown for multi-step tasks
        if len(goal_parts) > 1:
            parts.append("")
            parts.append("📋 GOAL BREAKDOWN (complete ALL parts):")
            for i, gp in enumerate(goal_parts, 1):
                parts.append(f"   {i}. {gp}")
            parts.append("")
            parts.append("⚠️ DO NOT mark done until ALL parts above are complete!")
        
        parts.extend([
            "=" * 50,
            "",
            f"**Current URL:** {observation.get('url', '')}",
            f"**Page Title:** {observation.get('title', '')}",
            f"**Step:** {observation.get('step_number', 0)} / {self.max_steps}",
        ])
        
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
        
        # *** OVERLAY/CONSENT DIALOG DETECTION ***
        overlay_info = observation.get('overlay_info')
        if overlay_info and overlay_info.get('detected'):
            parts.append("\n" + "🚨" * 20)
            parts.append("🍪 COOKIE CONSENT / OVERLAY DIALOG DETECTED!")
            parts.append(f"   Type: {overlay_info.get('type', 'unknown')}")
            if overlay_info.get('selector'):
                parts.append(f"   Selector: {overlay_info.get('selector')}")
            parts.append("")
            parts.append("   ⚠️ YOU MUST CLICK A CONSENT BUTTON FIRST!")
            parts.append("   Look for buttons with text like 'Accept all', 'Reject all', 'I agree'")
            parts.append("   These are typically at the TOP of the element list with type='consent_button'")
            parts.append("🚨" * 20)
        
        # *** AUTO-DEBUG: Detect stuck agent patterns ***
        step = observation.get('step_number', 0)
        elements = observation.get("elements", [])
        
        # Check if agent seems stuck (high step count, low element count, recent failures)
        recent_failures = sum(1 for ah in action_history[-3:] if not ah.get('success', True)) if action_history else 0
        if step > 5 and (len(elements) == 0 or recent_failures >= 2):
            parts.append("\n" + "⚠️" * 20)
            parts.append("🔧 AUTO-DEBUG DIAGNOSTICS:")
            parts.append(f"   • Step count: {step} (high)")
            parts.append(f"   • Elements found: {len(elements)}")
            parts.append(f"   • Recent failures: {recent_failures}")
            if len(elements) == 0:
                parts.append("   → NO ELEMENTS: Page may not be loaded or is blocking automation")
                parts.append("   → Try: wait action, or navigate to a different URL")
            if recent_failures >= 2:
                parts.append("   → REPEATED FAILURES: Change your approach!")
                parts.append("   → Try: different selector, different action, or mark done")
            parts.append("⚠️" * 20)
        
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
        if elements:
            parts.append("\n**Actionable Elements:**")
            for i, elem in enumerate(elements[:20]):  # Limit to 20 elements
                selector = elem.get("selector", "")
                text = elem.get("text", "")[:50]  # Truncate
                tag = elem.get("tag", "")
                parts.append(f"  {i+1}. [{tag}] {selector} — \"{text}\"")
        else:
            parts.append("\n**⚠️ NO ACTIONABLE ELEMENTS FOUND**")
            parts.append("   The page may be loading or blocking automation.")
        
        # Add error if present
        if observation.get("error"):
            parts.append(f"\n**Error:** {observation['error']}")
        
        # EXPLICIT completion check instruction
        current_url = observation.get('url', '')
        parts.append("\n" + "=" * 50)
        parts.append("🔍 COMPLETION CHECK:")
        parts.append(f"   Current URL: {current_url}")
        
        # Check if this looks like a search results page
        if 'search?q=' in current_url or '/search?' in current_url:
            parts.append("   ✅ URL shows SEARCH RESULTS PAGE!")
            parts.append("   → If goal was 'search X', respond with {\"action\": \"done\", \"done\": true}")
        
        parts.append("\n   ⚠️ If the GOAL is achieved, you MUST respond with:")
        parts.append('   {"thought": "Goal achieved", "action": "done", "done": true}')
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
    
    def reset(self, new_session_id: Optional[str] = None):
        """Reset agent state for new session.
        
        Args:
            new_session_id: Optional new session ID. If provided, updates session.
        """
        self._current_goal = None
        
        # Clear Agent's chat_history to prevent context pollution between sessions
        if self._agent is not None:
            self._agent.chat_history = []
            logger.info(f"Cleared chat_history for new session")
        
        # Update session_id if provided
        if new_session_id:
            self.session_id = new_session_id
