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
        # === CORE ACTION FIELDS ===
        thought: str = Field(description="Brief reasoning for this action")
        action: Literal["type", "submit", "click", "scroll", "navigate", "done", "wait", "clear_input"] = Field(
            description="Action to perform. Use 'clear_input' to fix garbled text in input fields."
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
        
        # === GOAL PROGRESS TRACKING ===
        goal_progress: Optional[int] = Field(
            None,
            description="Estimated % progress toward goal (0-100). E.g. 50 if halfway done."
        )
        page_summary: Optional[str] = Field(
            None,
            description="Brief description of what's visible on the page relevant to the goal"
        )
        on_track: Optional[bool] = Field(
            None,
            description="True if progressing toward goal as planned, False if off track"
        )
        
        # === ERROR/ANOMALY DETECTION (CRITICAL!) ===
        error_detected: Optional[bool] = Field(
            None,
            description="True if you notice ANY error: garbled text in inputs, wrong page loaded, element missing, popup blocking, etc."
        )
        error_description: Optional[str] = Field(
            None,
            description="Description of the error if error_detected=True. E.g. 'Input field shows garbled text: abc123abc' or 'Expected Wikipedia but still on Google'"
        )
        input_field_value: Optional[str] = Field(
            None,
            description="EXACT text you see in any input field on the page (copy what's visible, including if garbled)"
        )
        expected_vs_actual: Optional[str] = Field(
            None,
            description="What you expected to see vs what you actually see. E.g. 'Expected: wikipedia | Actual: googlegoogle'"
        )
        blockers: Optional[str] = Field(
            None,
            description="Anything blocking progress: popups, consent dialogs, captchas, login walls, etc."
        )
        retry_reason: Optional[str] = Field(
            None,
            description="If retrying a failed action, explain what went wrong and why retrying"
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
    "clear_input": "clear_input",  # New: for fixing garbled input text
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
- **clear_input**: Clear an input field completely (use when you see garbled/duplicated text!)
- **done**: Task complete - use ONLY when ALL parts of the goal are achieved

## CRITICAL: Error Detection AND RECOVERY (YOU MUST DO THIS!)

⚠️ **LOOK AT THE SCREENSHOT CAREFULLY!** Before each action, check for:

1. **Input Field Errors**: Is there GARBLED or DUPLICATED text in any input field?
   - Example of ERROR: "search termsearch termsearch term" (duplicated!)
   - Example of ERROR: "wikipediawikipedia" (typed twice!)
   - If you see garbled text: 
     a) Set `error_detected: true` and describe in `error_description`
     b) Set `input_field_value` to EXACTLY what you see
     c) **USE `clear_input` ACTION TO FIX IT!** Don't keep typing - CLEAR FIRST!

2. **Wrong Page/State**: Did the previous action work?
   - Are you on the expected page? If not, report in `expected_vs_actual`
   - Example: "Expected: Wikipedia homepage | Actual: Still on Google search results"
   - **If wrong page, try clicking the correct link again!**

3. **Progress Tracking**: How close are you to completing the goal?
   - Set `goal_progress` to 0-100 (percentage complete)
   - Set `on_track: false` if something went wrong

4. **Blockers**: Is anything blocking you?
   - Report popups, consent dialogs, login walls in `blockers`

## CRITICAL: ERROR RECOVERY - DON'T JUST REPORT, FIX!

If you detect an error, you MUST take corrective action:
- **Garbled text in input** → Use `clear_input` action to clear it, then type again
- **Clicked link but still on same page** → Try clicking again or use a different selector
- **Typed but text didn't appear** → Clear and retype
- **Submit didn't work** → Try clicking the submit button instead
- **On unexpected/wrong page** → Use `navigate` action to go back to the right URL!
  - Example: Goal is "search on google" but you see amazon.com → navigate to google.com
  - Example: You were clicking a link but ended up on random page → navigate back

DO NOT keep repeating the same failed action. ADAPT!

## CRITICAL: ANTI-LOOP RULES (NEVER VIOLATE!)

⚠️ **NEVER repeat the EXACT SAME action twice in a row!** If you just did:
- `type → #searchInput = "term"` → NEXT must be `submit` or `click`, NOT another type!
- `click → a.link` → Don't click the same link again if it didn't work
- `submit → #form` → Don't submit again if page didn't change

### Type + Submit Workflow
After typing text into an input field, you MUST either:
1. Use `submit` action to press Enter, OR
2. Click a search/submit button

WRONG: type → type → type → type (stuck in loop!)
RIGHT: type → submit → click → done

If you've typed the SAME value 2+ times without result:
→ The input probably worked! Use `submit` or `click` a button to proceed!


## CRITICAL: Recovery from Unexpected Navigation

If the current URL doesn't match what you expect for your goal:
1. Set `error_detected: true`
2. Set `expected_vs_actual` to describe the mismatch (e.g., "Expected: google.com | Actual: amazon.com")
3. Set `on_track: false`
4. Use `navigate` action to go to the correct URL

Example: If your goal is "search for python on google" but the page shows facebook.com:
→ Use `navigate` with `url: "https://www.google.com"` to get back on track!


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

## Response Format (COMPLETE JSON with ALL fields!)
```json
{
  "thought": "Brief reasoning - what part of the goal am I working on?",
  "action": "type|submit|click|scroll|navigate|done",
  "selector": "exact selector from element list",
  "value": "text to type (for type action)",
  "done": true or false,
  "summary": "What was accomplished (REQUIRED when done=true)",
  "goal_progress": 0-100,
  "on_track": true or false,
  "error_detected": true if you see ANY error (garbled text, wrong page, etc),
  "error_description": "Describe the error if error_detected is true",
  "input_field_value": "EXACT text visible in any input field on the page",
  "expected_vs_actual": "What you expected vs what you actually see",
  "blockers": "Any popups/dialogs/issues blocking progress"
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
        logger.info(f"[AGENT][ENTRY] __init__:agent.py model={model}, max_steps={max_steps}, session_id={session_id}")
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self.session_id = session_id
        self._agent = None
        self._current_goal: Optional[str] = None
        # Track action history internally - prevents duplicate actions
        self._action_history: List[Dict[str, Any]] = []
        logger.debug(f"[AGENT][EXIT] __init__:agent.py → BrowserAgent created")
    
    def _ensure_agent(self):
        """Lazily initialize the PraisonAI agent."""
        if self._agent is not None:
            return
        
        logger.debug(f"[AGENT][CALL] _ensure_agent:agent.py → Creating PraisonAI Agent with model={self.model}")
        
        try:
            from praisonaiagents import Agent
        except ImportError:
            logger.error(f"[AGENT][ERROR] _ensure_agent:agent.py → praisonaiagents not installed")
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
        logger.debug(f"[AGENT][EXIT] _ensure_agent:agent.py → Agent created successfully")
    
    def set_goal(self, goal: str) -> None:
        """Set current goal and clear history if goal changed.
        
        Call this before process_observation when starting a new goal.
        Clears action history so old actions don't confuse the agent.
        """
        if goal != self._current_goal:
            logger.info(f"[AGENT][GOAL] set_goal:agent.py → New goal, clearing history. old='{self._current_goal}', new='{goal[:50]}...'")
            self._action_history = []
        self._current_goal = goal
    
    def clear_history(self) -> None:
        """Clear action history explicitly."""
        self._action_history = []
        logger.debug(f"[AGENT][CLEAR] clear_history:agent.py → History cleared")

    
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
        
        import time
        start_time = time.time()
        step_number = observation.get('step_number', 0)
        url = observation.get('url', 'unknown')[:40]
        elements_count = len(observation.get('elements', []))
        
        logger.info(f"[AGENT][ENTRY] process_observation:agent.py step={step_number}, url='{url}...', elements={elements_count}")
        
        # Build observation prompt
        logger.debug(f"[AGENT][CALL] _build_prompt:agent.py elements={elements_count}")
        prompt = self._build_prompt(observation)
        logger.debug(f"[AGENT][DATA] _build_prompt:agent.py prompt_length={len(prompt)} chars")
        
        # Check if we have a screenshot for vision-based decision making
        screenshot_base64 = observation.get('screenshot')
        # Enable vision for models that support it: GPT-4, GPT-4o, Gemini, Claude, etc.
        model_lower = self.model.lower()
        vision_capable = any(m in model_lower for m in ['gpt-4', 'gpt-4o', 'gemini', 'claude'])
        use_vision = screenshot_base64 and vision_capable
        
        # Flow tracing for vision decision
        logger.info(f"[AGENT][DECISION] process_observation:agent.py model={self.model}, vision_capable={vision_capable}, has_screenshot={bool(screenshot_base64)}, use_vision={use_vision}")
        if screenshot_base64:
            logger.debug(f"[AGENT][DATA] process_observation:agent.py screenshot_size={len(screenshot_base64)} chars")

        
        # Get agent response with structured output if available
        try:
            action_model = get_browser_action_model()
            
            if use_vision:
                # Use LiteLLM directly for vision with structured output
                # Agent.chat(attachments+output_pydantic) combo doesn't work reliably
                from litellm import completion
                
                logger.info(f"[AGENT][CALL] litellm.completion:agent.py model={self.model}, mode=vision+structured")
                
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
                
                llm_start = time.time()
                try:
                    # Use response_format for structured output if model supports it
                    if action_model is not None:
                        response = completion(
                            model=self.model,
                            messages=messages,
                            max_tokens=500,
                            response_format=action_model,  # Structured output!
                        )
                    else:
                        response = completion(
                            model=self.model,
                            messages=messages,
                            max_tokens=500,
                        )
                    llm_elapsed = time.time() - llm_start
                    
                    response_content = response.choices[0].message.content
                    usage = getattr(response, 'usage', None)
                    tokens_used = usage.total_tokens if usage else 0
                    
                    logger.info(f"[AGENT][RECV] litellm.completion:agent.py time={llm_elapsed:.2f}s, tokens={tokens_used}")
                    
                    if response_content is None:
                        raise ValueError("LLM returned empty response")
                    
                    # Parse response - could be JSON string
                    action = self._parse_response(response_content.strip())
                    logger.debug(f"[AGENT][DATA] parsed action={action.get('action', 'N/A')}, selector={action.get('selector', 'N/A')[:30] if action.get('selector') else 'N/A'}")
                    
                except Exception as vision_error:
                    logger.warning(f"[AGENT][WARN] Vision failed, falling back to text-only: {vision_error}")
                    response = self._agent.chat(prompt)
                    action = self._parse_response(str(response))

                
            elif action_model is not None:
                # Use Pydantic model for guaranteed structured output
                logger.info(f"[AGENT][CALL] Agent.chat:agent.py model={self.model}, mode=pydantic")
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
                logger.debug(f"[AGENT][RECV] Agent.chat:agent.py action={action.get('action', 'N/A')}")
            else:
                # Fallback to string parsing
                logger.info(f"[AGENT][CALL] Agent.chat:agent.py model={self.model}, mode=string")
                response = self._agent.chat(prompt)
                action = self._parse_response(response)
                logger.debug(f"[AGENT][RECV] Agent.chat:agent.py action={action.get('action', 'N/A')}")
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[AGENT][ERROR] process_observation:agent.py → {type(e).__name__}: {e}, elapsed={elapsed:.2f}s")
            action = {
                "thought": f"Error processing observation: {e}",
                "action": "wait",
                "done": False,
                "error": str(e),
            }
        
        # Normalize action name to valid CDP action type
        # LLMs often return freeform text like "enter text and submit" instead of "type"
        action = normalize_action(action)
        
        # Record action to internal history for deduplication
        step_number = observation.get('step_number', 0)
        self._action_history.append({
            'step': step_number,
            'action': action.get('action'),
            'selector': action.get('selector', ''),
            'value': action.get('value', ''),
            'done': action.get('done', False),
        })
        # Keep only last 10 actions to prevent memory bloat
        if len(self._action_history) > 10:
            self._action_history = self._action_history[-10:]
        
        elapsed = time.time() - start_time
        logger.info(f"[AGENT][EXIT] process_observation:agent.py → action={action.get('action', 'N/A')}, done={action.get('done', False)}, elapsed={elapsed:.2f}s")
        
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
        
        # ===== INTERNAL ACTION HISTORY (prevents duplicate actions) =====
        # Use our internal _action_history which tracks all actions across steps
        if self._action_history:
            parts.append("\n" + "=" * 40)
            parts.append("📜 YOUR PREVIOUS ACTIONS (DO NOT REPEAT UNNECESSARILY):")
            for ah in self._action_history[-5:]:  # Last 5 actions
                step = ah.get('step', '?')
                action_type = ah.get('action', 'unknown')
                selector = ah.get('selector', '')[:35]
                value = ah.get('value', '')
                if value:
                    parts.append(f"   Step {step}: {action_type} → {selector} = \"{value}\"")
                else:
                    parts.append(f"   Step {step}: {action_type} → {selector}")
            parts.append("")
            parts.append("⚠️ If you already typed text in an input, do NOT type again!")
            parts.append("⚠️ If you already submitted, check if you need to click next!")
            parts.append("=" * 40)
        
        # Add action history from observation if present (fallback)
        action_summary = observation.get('action_summary', '')
        action_history = observation.get('action_history', [])
        
        if action_summary:
            parts.append(f"\n**{action_summary}**")
        elif action_history and not self._action_history:
            parts.append("\n**Recent Actions:**")
            for ah in action_history[-5:]:  # Last 5 actions
                status = "✓" if ah.get('success') else "✗"
                parts.append(f"  {status} {ah.get('action')}: {ah.get('selector', '')[:40]}")
        
        # Check if consent was already handled
        consent_already_handled = any(
            'consent' in str(ah.get('selector', '')).lower() or 
            'consent' in str(ah.get('thought', '')).lower() or
            'accept' in str(ah.get('selector', '')).lower() or
            'reject' in str(ah.get('selector', '')).lower()
            for ah in action_history if ah.get('success', True)
        )
        
        # *** OVERLAY/CONSENT DIALOG DETECTION ***
        overlay_info = observation.get('overlay_info')
        if overlay_info and overlay_info.get('detected') and not consent_already_handled:
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
        elif consent_already_handled:
            parts.append("\n✅ CONSENT ALREADY HANDLED - Do NOT click consent buttons again. Proceed with your task.")
        
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
