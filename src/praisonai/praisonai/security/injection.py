"""
Prompt injection defense for PraisonAI agents.

Implements a 6-check detection pipeline adapted from production
sovereign-agent security research. Works as a PraisonAI hook
registered on BEFORE_TOOL and BEFORE_AGENT events.

Zero overhead when not enabled — all imports are local.
"""
import re
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, List, Optional, Any

logger = logging.getLogger(__name__)

# ─── Threat Classification ────────────────────────────────────────────────────

class ThreatLevel(IntEnum):
    """Severity of detected injection attempt."""
    LOW = 0       # Log only; no action
    MEDIUM = 1    # Log + warn; continue
    HIGH = 2      # Log + warn; sanitize
    CRITICAL = 3  # Block execution entirely


# ─── Detection Pattern Sets ───────────────────────────────────────────────────

_INSTRUCTION_PATTERNS: List[str] = [
    r"ignore\s+(all\s+)?(previous|prior|earlier|above)\s+(instructions?|directives?|rules?|prompts?)",
    r"disregard\s+(your\s+)?(previous|prior|earlier|above|all|system|prompt|instructions?)",
    r"forget\s+(everything|all|your)\s+(you\s+)?(know|were\s+told|learned)",
    r"(new|updated?|revised?)\s+instructions?\s*(are|:)",
    r"you\s+are\s+now\s+",
    r"you\s+must\s+now\s+",
    r"override\s+(your\s+)?(guidelines?|rules?|instructions?|directives?)",
    r"act\s+as\s+if\s+you\s+(have\s+no|don'?t\s+have)\s+(restrictions?|rules?|guidelines?)",
    r"pretend\s+(you\s+are|to\s+be)\s+",
    r"roleplay\s+as\s+",
    r"DAN\s*[\-:,]",       # "Do Anything Now" jailbreak
    r"jailbreak",
    r"your\s+true\s+self",
    r"developer\s+mode\s+enabled",
    r"unrestricted\s+mode",
]

_AUTHORITY_PATTERNS: List[str] = [
    r"i\s+am\s+(your\s+)?(creator|developer|owner|admin|administrator|operator|god|master)",
    r"i\s+am\s+the\s+(developer|creator|owner|admin|administrator)\s+(of|for)\s+(this|the)\s+system",
    r"as\s+(your|the)\s+(creator|developer|owner|admin|administrator|system|openai|anthropic|google)",
    r"message\s+from\s+(openai|anthropic|google|microsoft|your\s+creator|your\s+developer)",
    r"this\s+is\s+(openai|anthropic|google|your\s+creator|your\s+developer|your\s+owner)",
    r"(openai|anthropic|google)\s+(hereby|grants?|allows?|authorizes?)",
    r"system\s+override\s+(by|from|authorized)",
    r"root\s+access\s+granted",
    r"(elevated|admin)\s+privilege",
]

_BOUNDARY_PATTERNS: List[str] = [
    r"</?(system|human|assistant|user|prompt|instruction)\s*>",
    r"\[/?(SYSTEM|HUMAN|ASSISTANT|USER|PROMPT|INST)\]",
    r"---+\s*(END|STOP|IGNORE|NEW)\s+(SYSTEM|PROMPT|INSTRUCTIONS?)\s*---+",
    r"={3,}\s*(END|STOP|IGNORE)\s+(SYSTEM|PROMPT)\s*={3,}",
    r"<\|im_start\|>|<\|im_end\|>",    # OpenAI ChatML boundary tags
    r"<<SYS>>|<</SYS>>",               # Llama system tags
    r"\[INST\]|\[/INST\]",             # Llama instruction tags
    r"###\s*(Human|Assistant|System):",
]

_OBFUSCATION_PATTERNS: List[str] = [
    r"0x[0-9a-fA-F]{16,}",            # Long hex strings (potential encoding)
    r"\\u[0-9a-fA-F]{4}(\\u[0-9a-fA-F]{4}){4,}",  # Unicode escape sequences
    r"\.(decode|encode)\(['\"]base64['\"]",         # Base64 decode calls
]

_FINANCIAL_PATTERNS: List[str] = [
    r"transfer\s+(funds?|money|\$|usdc|eth|btc|crypto|\d+)",
    r"send\s+(money|\$|usdc|eth|btc|funds?|crypto|payment|\$?\d+)\s+(to|into)",
    r"send\s+.{0,20}\s+to\s+(my|your|their|the)?\s*wallet",
    r"(approve|authorize|confirm)\s+(this\s+)?(payment|transaction|transfer)",
    r"(buy|purchase|acquire)\s+(bitcoin|eth|crypto|usdc)\s+(with|using)\s+(all|my|your)",
    r"wire\s+(transfer|funds?)",
    r"withdraw\s+(all|funds?|balance)",
    r"drain\s+(wallet|account|funds?|balance)",
]

_SELF_HARM_PATTERNS: List[str] = [
    r"(delete|destroy|erase|wipe|remove)\s+(yourself|your\s+(data|memory|files|code|database))",
    r"(shutdown|shut\s+down|terminate|kill)\s+(yourself|your\s+(process|runtime|server)|immediately)",
    r"shut\s+down\s+(immediately|now|completely)",
    r"erase\s+(all|your)\s+(memory|data|history)",
    r"erase\s+all\s+your\s+",
    r"rm\s+-rf\s+[/~]",               # Destructive shell command
    r"drop\s+(database|table|schema)\s+",  # SQL destruction
    r"format\s+(c:|/dev/sd[a-z])",    # Disk format
    r"self[\s-]?destruct",
    r"(corrupt|destroy)\s+(your\s+)?(state|database|config|wallet)",
]

_LONG_B64_RE = re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$")

# Trust sources that bypass injection scanning
_TRUSTED_SOURCES = frozenset([
    "trusted_tool", "internal", "system", "praisonai_core",
])


# ─── Detection Functions ──────────────────────────────────────────────────────

def detect_instruction_patterns(text: str) -> bool:
    """Check 1: Instruction override / jailbreak patterns."""
    for pat in _INSTRUCTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def detect_authority_claims(text: str) -> bool:
    """Check 2: Fake authority / impersonation patterns."""
    for pat in _AUTHORITY_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def detect_boundary_manipulation(text: str) -> bool:
    """Check 3: Prompt boundary injection (fake system/human/assistant tags)."""
    for pat in _BOUNDARY_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def detect_obfuscation(text: str) -> bool:
    """Check 4: Encoding/obfuscation tricks (base64, hex, unicode escapes)."""
    # Long hex strings
    for pat in _OBFUSCATION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    # Long base64-like blobs (≥40 chars of valid b64 chars)
    stripped = text.strip()
    if _LONG_B64_RE.match(stripped) and len(stripped) >= 40:
        return True
    return False


def detect_financial_manipulation(text: str) -> bool:
    """Check 5: Unauthorized financial / crypto manipulation patterns."""
    for pat in _FINANCIAL_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def detect_self_harm_instructions(text: str) -> bool:
    """Check 6: Instructions to destroy agent data, shutdown, or wipe memory."""
    for pat in _SELF_HARM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


# ─── ScanResult ───────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    """Result of scanning a text for injection threats."""
    threat_level: ThreatLevel
    blocked: bool
    checks_triggered: List[str] = field(default_factory=list)
    source: str = "external"
    text_preview: str = ""

    @property
    def is_safe(self) -> bool:
        return self.threat_level == ThreatLevel.LOW

    def __repr__(self) -> str:
        return (
            f"ScanResult(level={self.threat_level.name}, blocked={self.blocked}, "
            f"checks={self.checks_triggered})"
        )


def scan_text(text: str, source: str = "external") -> ScanResult:
    """
    Run all 6 injection checks on a text string.

    Args:
        text: The text to scan.
        source: Source of the text. Trusted sources bypass blocking.
                Values: 'external' (default), 'trusted_tool', 'internal'.

    Returns:
        ScanResult with threat level and triggered checks.

    Example:
        >>> result = scan_text("Ignore all previous instructions")
        >>> result.threat_level
        <ThreatLevel.HIGH: 2>
    """
    if not text or not isinstance(text, str):
        return ScanResult(ThreatLevel.LOW, blocked=False, source=source)

    # Trusted sources: scan but never block
    is_trusted = source in _TRUSTED_SOURCES

    triggered = []
    if detect_instruction_patterns(text):
        triggered.append("instruction_override")
    if detect_authority_claims(text):
        triggered.append("authority_claim")
    if detect_boundary_manipulation(text):
        triggered.append("boundary_manipulation")
    if detect_obfuscation(text):
        triggered.append("obfuscation")
    if detect_financial_manipulation(text):
        triggered.append("financial_manipulation")
    if detect_self_harm_instructions(text):
        triggered.append("self_harm_instruction")

    count = len(triggered)
    if count == 0:
        level = ThreatLevel.LOW
    elif count == 1:
        # Single check: HIGH for dangerous categories, MEDIUM for others
        dangerous = {"financial_manipulation", "self_harm_instruction", "instruction_override"}
        level = ThreatLevel.HIGH if triggered[0] in dangerous else ThreatLevel.MEDIUM
    elif count == 2:
        level = ThreatLevel.HIGH
    else:
        level = ThreatLevel.CRITICAL

    # Trusted sources are never blocked regardless of level
    blocked = (level >= ThreatLevel.CRITICAL) and not is_trusted

    if triggered:
        logger.warning(
            "[praisonai.security] Injection detected | source=%s level=%s checks=%s preview=%r",
            source, level.name, triggered, text[:80],
        )

    return ScanResult(
        threat_level=level,
        blocked=blocked,
        checks_triggered=triggered,
        source=source,
        text_preview=text[:100],
    )


# ─── InjectionDefense Class ───────────────────────────────────────────────────

class InjectionDefense:
    """
    Injection defense that integrates with PraisonAI's hook system.

    Scans tool inputs and agent prompts for prompt injection attempts
    and blocks critical threats before they reach the LLM.

    Example:
        >>> defense = InjectionDefense()
        >>> hook = defense.create_hook()
        >>> # Register with agent:
        >>> from praisonaiagents.hooks import add_hook
        >>> add_hook("before_tool", hook)
    """

    def __init__(
        self,
        extra_patterns: Optional[List[str]] = None,
        block_threshold: ThreatLevel = ThreatLevel.CRITICAL,
        trusted_sources: Optional[List[str]] = None,
    ):
        """
        Args:
            extra_patterns: Additional regex patterns to include in Check 1.
            block_threshold: Minimum threat level that causes blocking.
                             Default: CRITICAL (only block if 3+ checks fire).
            trusted_sources: Source names that bypass blocking.
        """
        self._extra_patterns = extra_patterns or []
        self._block_threshold = block_threshold
        self._trusted_sources = frozenset(trusted_sources or []) | _TRUSTED_SOURCES

    def scan(self, text: str, source: str = "external") -> ScanResult:
        """
        Scan text through the 6-check pipeline.

        Args:
            text: Text to scan.
            source: Source identifier ('external', 'trusted_tool', etc.)

        Returns:
            ScanResult with threat classification.
        """
        result = scan_text(text, source=source)

        # Apply extra patterns as Check 1 extension
        if self._extra_patterns and text:
            for pat in self._extra_patterns:
                if re.search(pat, text, re.IGNORECASE):
                    if "extra_pattern" not in result.checks_triggered:
                        result.checks_triggered.append("extra_pattern")
                    # Escalate if extra pattern fires
                    if result.threat_level < ThreatLevel.MEDIUM:
                        result.threat_level = ThreatLevel.MEDIUM
                    break

        # Re-evaluate blocking with custom threshold
        is_trusted = source in self._trusted_sources
        result.blocked = (result.threat_level >= self._block_threshold) and not is_trusted

        return result

    def _extract_strings(self, obj: Any, depth: int = 0) -> List[str]:
        """Recursively extract string values from a dict/list/str."""
        if depth > 4:
            return []
        strings = []
        if isinstance(obj, str):
            strings.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                strings.extend(self._extract_strings(v, depth + 1))
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                strings.extend(self._extract_strings(item, depth + 1))
        return strings

    def create_hook(self) -> Callable:
        """
        Create a BEFORE_TOOL hook function for use with PraisonAI's hook system.

        Returns:
            Hook function that accepts BeforeToolInput and returns HookResult or None.

        Example:
            >>> from praisonaiagents.hooks import add_hook
            >>> defense = InjectionDefense()
            >>> add_hook("before_tool", defense.create_hook())
        """
        defense = self

        def _injection_hook(data: Any):
            # Lazily import to avoid circular at module load
            from praisonaiagents.hooks import HookResult

            # Extract all string values from tool_input dict
            strings = defense._extract_strings(getattr(data, "tool_input", {}))
            # Also check the prompt if this is a before_agent event
            prompt = getattr(data, "prompt", "")
            if prompt:
                strings.append(prompt)

            # Determine source: tool calls from agent internals are semi-trusted
            source = getattr(data, "_source", "external")

            for text in strings:
                if not text:
                    continue
                result = defense.scan(text, source=source)
                if result.blocked:
                    logger.warning(
                        "[praisonai.security] Blocking tool=%s agent=%s checks=%s",
                        getattr(data, "tool_name", "?"),
                        getattr(data, "agent_name", "?"),
                        result.checks_triggered,
                    )
                    return HookResult(
                        decision="block",
                        reason=(
                            f"Injection defense: {', '.join(result.checks_triggered)} "
                            f"[{result.threat_level.name}]"
                        ),
                    )
            return None  # Allow

        return _injection_hook

    def create_agent_hook(self) -> Callable:
        """
        Create a BEFORE_AGENT hook that scans the incoming user prompt.

        Returns:
            Hook function for BEFORE_AGENT events.
        """
        defense = self

        def _agent_injection_hook(data: Any):
            from praisonaiagents.hooks import HookResult

            prompt = getattr(data, "prompt", "")
            if not prompt:
                return None

            result = defense.scan(prompt, source="external")
            if result.blocked:
                logger.warning(
                    "[praisonai.security] Blocking agent prompt agent=%s checks=%s",
                    getattr(data, "agent_name", "?"),
                    result.checks_triggered,
                )
                return HookResult(
                    decision="block",
                    reason=(
                        f"Injection defense (prompt): {', '.join(result.checks_triggered)} "
                        f"[{result.threat_level.name}]"
                    ),
                )
            return None

        return _agent_injection_hook
