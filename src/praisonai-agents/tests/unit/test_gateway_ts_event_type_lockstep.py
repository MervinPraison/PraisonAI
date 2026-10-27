"""The TypeScript client's ``GatewayEventType`` must mirror Python's ``EventType``.

The gateway wire event vocabulary is defined once in
``praisonaiagents/gateway/protocols.py`` and re-declared in
``praisonai-ts/src/gateway/index.ts``. Nothing else ties the two together, so an
event type added (or renamed) on the Python side would otherwise reach the TS
client only as silently ignored or misrouted frames at runtime.

This is a lockstep test: it asserts that the two independently-maintained lists
agree member-for-member (name and wire value), so drift fails CI instead.
"""

import re
from pathlib import Path

import pytest

from praisonaiagents.gateway.protocols import EventType

_TS_GATEWAY = (
    Path(__file__).resolve().parents[3]
    / "praisonai-ts"
    / "src"
    / "gateway"
    / "index.ts"
)


_TS_MEMBER = re.compile(r"""([A-Za-z_$][\w$]*)\s*=\s*(['"])(.*?)\2""", re.S)


def _parse_ts_enum(source: str) -> dict[str, str]:
    """Parse ``export enum GatewayEventType { NAME = 'value', ... }`` from TS source.

    Every enum member must be a ``NAME = 'value'`` (or double-quoted) pair; any
    other entry fails loudly rather than being silently skipped.
    """
    body = re.search(r"export enum GatewayEventType\s*\{(.*?)\n\}", source, re.S)
    assert body, "GatewayEventType enum not found"
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", body.group(1), flags=re.S)
    members = {}
    for entry in filter(None, (e.strip() for e in text.split(","))):
        match = _TS_MEMBER.fullmatch(entry)
        assert match, f"Unparseable GatewayEventType entry: {entry!r}"
        members[match.group(1)] = match.group(3)
    return members


def _ts_event_types() -> dict[str, str]:
    return _parse_ts_enum(_TS_GATEWAY.read_text(encoding="utf-8"))


def test_parse_ts_enum_rejects_or_captures_every_entry():
    src = """export enum GatewayEventType {
  // comment
  A = 'a',
  MESSAGE_V2 = 'message_v2',
  B = "b",
}"""
    assert _parse_ts_enum(src) == {"A": "a", "MESSAGE_V2": "message_v2", "B": "b"}
    with pytest.raises(AssertionError, match="Unparseable"):
        _parse_ts_enum("export enum GatewayEventType {\n  A = 'a',\n  C,\n}")


@pytest.mark.skipif(not _TS_GATEWAY.exists(), reason="TypeScript SDK not present")
def test_ts_gateway_event_type_matches_python():
    python = {member.name: member.value for member in EventType}
    ts = _ts_event_types()

    missing_in_ts = sorted(set(python) - set(ts))
    extra_in_ts = sorted(set(ts) - set(python))
    mismatched = sorted(n for n in set(python) & set(ts) if python[n] != ts[n])

    assert not (missing_in_ts or extra_in_ts or mismatched), (
        "praisonai-ts GatewayEventType drifted from praisonaiagents EventType: "
        f"missing in TS={missing_in_ts}, extra in TS={extra_in_ts}, "
        f"value mismatch={mismatched}. Update src/praisonai-ts/src/gateway/index.ts."
    )
