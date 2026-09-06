"""
Behaviour parity: options accepted for Python parity that are not yet acted on.

The other two layers measure PRESENCE. The name tracker asks whether an export
exists; the signature checker asks whether a parameter exists. An option that is
accepted, typed, documented and then ignored passes both -- which is how 76 of
them accumulated without any number moving.

This layer counts them. The source is the `UNHONOURED_OPTIONS` ledger in
src/praisonai-ts/src/utils/parity-notice.ts, which the TypeScript surfaces
iterate at runtime, so every option listed there does announce itself when it is
passed.

The gate is a ratchet: the committed report carries the total, and `--check`
fails if the current total is HIGHER. Closing an option lowers it; accepting a
new one without implementing it raises it and reddens the build. `--write`
enforces the same ratchet -- it runs on every push to main and auto-commits, so
without that a rise reached the floor by being written rather than argued for.
Pass `--allow-growth` to bank a rise deliberately, with a reason in the pull
request. Lowering the total never needs a flag.

    python -m praisonai._dev.parity.behaviour --write
    python -m praisonai._dev.parity.behaviour --check

Two things this file is careful about, both learned the hard way:

* A surface that falls OUT of the parse lowers the total, which reads as
  progress and is bankable. So the literal is scanned structurally rather than
  line-shaped, and the result is cross-checked against an independent scan of
  the same text and against every `unhonouredFor('X')` call site. A surface the
  ledger still declares but the parse did not see is an error, never a closure.

* What this CANNOT check is that a deleted entry was really implemented. The
  ledger is hand-written; delete three names and the total falls with the
  TypeScript untouched. Three candidate guards were measured against the 48
  entries that stand today, and none is worth shipping:

    - "the option is referenced in src/ outside parity-notice.ts": 0 of 48
      would flag. The signature gate REQUIRES the parameter to exist, so this
      cannot fail.
    - "some test names the option": 0 of 48 would flag. Cannot fail either.
    - "some test that does not import parity-notice names the option": 7 of 48
      would flag, so it can fail -- but the other 41 pass on a bare identifier
      occurring anywhere in the test tree, about any surface. `Task.web` is
      "evidenced" by tools/registry.test.ts, `AgentTeam.autonomy` by a test of
      Agent.autonomy, `Task.caching` by cli-features.test.ts. It would license
      85% of possible deletions while reading as verification, and a comment
      would satisfy it.

  So there is no guard, and the number stays honestly self-reported. `--write`
  and `--check` PRINT what a change claims to have closed, for a reviewer to
  check against a test, instead of pretending to verify it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ._paths import find_repo_root

LEDGER = 'src/praisonai-ts/src/utils/parity-notice.ts'
TS_SOURCE = 'src/praisonai-ts/src'
MD_OUTPUT = 'src/praisonai-ts/BEHAVIOUR_PARITY.md'
JSON_OUTPUT = 'src/praisonai-ts/behaviour-parity.json'

# `notYetHonoured('Surface', 'option', 'why')` with literal arguments: an option
# that works for some inputs and not others. Counted apart from the ledger,
# because the option is not wholly absent.
_PARTIAL_RE = re.compile(r"notYetHonoured\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,")
# `unhonouredFor('Surface')` with a literal argument: a surface the TypeScript
# code iterates at runtime. Every one of these must survive the parse.
_ITERATES_RE = re.compile(r"unhonouredFor\(\s*'([^']+)'\s*\)")
# Quoting is not the ledger's business: JavaScript accepts ' " and ` for both
# keys and option names, and a style that this file did not recognise would
# silently drop the surface -- which LOWERS the total and reads as progress.
_QUOTE = '\'"`'
_OPTION_RE = re.compile(r"([\'\"`])([A-Za-z_][A-Za-z0-9_]*)\1")
_ANY_STRING_RE = re.compile(r"([\'\"`])((?:[^\\\n]|\\.)*?)\1")
# An independent second opinion on which surfaces the literal declares, used
# only to cross-check the scanner below. Deliberately not the same technique.
# A JavaScript object key may be quoted OR a bare identifier: `Handoff: [...]`
# is as valid as `'Handoff': [...]`. Recognising only the quoted form let a bare
# key drop out of the parse -- which LOWERS the total and reads as progress.
_KEY_RE = re.compile(
    r"(?:([\'\"`])([^\'\"`\n]+)\1|([A-Za-z_$][\w$]*))\s*:\s*\["
)
# The start of one entry, matched at brace depth 0 by the scanner. Group 2 is a
# quoted key; group 3 is a bare identifier key.
_ENTRY_RE = re.compile(
    r"(?:([\'\"`])([^\'\"`\n]+)\1|([A-Za-z_$][\w$]*))\s*:\s*"
)
# A bare identifier at the top level of the literal, where the scanner meets a
# key that is not quoted.
_BARE_KEY_RE = re.compile(r"[A-Za-z_$][\w$]*")


@dataclass
class Behaviour:
    """What the TypeScript SDK accepts but does not yet act on."""

    surfaces: Dict[str, List[str]] = field(default_factory=dict)
    partial: List[Dict[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.surfaces.values())


class LedgerError(RuntimeError):
    """The ledger could not be read. Never reported as 'nothing left to do'."""


def _ledger_block(text: str) -> str:
    """The body of the UNHONOURED_OPTIONS object literal."""
    marker = 'export const UNHONOURED_OPTIONS'
    if marker not in text:
        raise LedgerError(
            f'{LEDGER} no longer declares {marker}. If it was renamed, update '
            'praisonai._dev.parity.behaviour to match -- a ledger this tool cannot '
            'read must never be reported as zero options outstanding.'
        )
    start = text.index(marker)
    open_brace = text.index('{', start)
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[open_brace + 1:i]
    raise LedgerError(f'the UNHONOURED_OPTIONS literal in {LEDGER} is not closed')


def _strip_comments(body: str) -> str:
    """Blank out // and /* */ comments, preserving every offset and quoted string.

    A commented-out entry must not be counted, and a real entry must not be lost
    because a comment sits beside it.
    """
    out: List[str] = []
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch in ("'", '"', '`'):
            j = i + 1
            while j < n and body[j] != ch:
                j += 2 if body[j] == '\\' else 1
            out.append(body[i:j + 1])
            i = j + 1
        elif body.startswith('//', i):
            j = body.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
        elif body.startswith('/*', i):
            j = body.find('*/', i)
            j = n if j < 0 else j + 2
            out.append(''.join(' ' if c != '\n' else '\n' for c in body[i:j]))
            i = j
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def _end_of_string(body: str, open_at: int) -> int:
    """Index of the quote that closes the string opened at ``open_at``."""
    quote = body[open_at]
    i = open_at + 1
    while i < len(body):
        if body[i] == '\\':
            i += 2
            continue
        if body[i] == quote:
            return i
        i += 1
    raise LedgerError(f'a quoted name in {LEDGER} is never closed')


def _matching_bracket(body: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(body)):
        if body[i] == '[':
            depth += 1
        elif body[i] == ']':
            depth -= 1
            if depth == 0:
                return i
    raise LedgerError(f'an entry in {LEDGER} opens a list that is never closed')


def _parse_entries(body: str) -> Dict[str, List[str]]:
    """Every `'Surface': [...]` entry at the top level of the literal.

    Structural, not line-shaped. The first version of this used a line-anchored
    regex that required a trailing comma after the closing bracket, so putting
    one entry on a single line without that comma silently deleted a whole
    surface -- reported as options CLOSED, and bankable with --write while the
    TypeScript was untouched. Anything this scanner cannot account for raises.
    """
    surfaces: Dict[str, List[str]] = {}
    i, n, depth = 0, len(body), 0
    while i < n:
        ch = body[i]
        if ch in '{[(':
            depth += 1
            i += 1
            continue
        if ch in '}])':
            depth -= 1
            i += 1
            continue
        if ch in _QUOTE and depth != 0:
            i = _end_of_string(body, i) + 1
            continue
        # At the top level a key opens an entry -- quoted (`'Surface':`) or a
        # bare JavaScript identifier (`Handoff:`). Both are valid and both must
        # be counted; a bare key that fell through would LOWER the total.
        if depth == 0 and (ch in _QUOTE or (ch.isalpha() or ch in '_$')):
            i = _consume_entry(body, i, surfaces)
            continue
        i += 1
    return surfaces


def _consume_entry(body: str, i: int, surfaces: Dict[str, List[str]]) -> int:
    """Read one top-level `Surface: [...]` entry starting at ``i``; return the
    index just past its closing bracket.

    ``Surface`` may be quoted or a bare identifier. Anything at the top level
    that is not such an entry raises, so a stray token can never quietly drop a
    surface from the count.
    """
    n = len(body)
    match = _ENTRY_RE.match(body, i)
    if not match:
        raise LedgerError(
            f'{LEDGER}: a token at the top level of UNHONOURED_OPTIONS near offset '
            f"{i} is not a `Surface: [...]` entry"
        )
    key = match.group(2) if match.group(2) is not None else match.group(3)
    value_at = match.end()
    if value_at >= n or body[value_at] != '[':
        raise LedgerError(
            f"{LEDGER}: the value of '{key}' is not a list of option names. "
            'Every entry must be `Surface: [ ... ]` so the options can be counted.'
        )
    close = _matching_bracket(body, value_at)
    if key in surfaces:
        raise LedgerError(
            f"{LEDGER}: surface '{key}' is declared twice; the second wins at "
            'runtime and the first is uncounted. Merge them.'
        )
    inner = body[value_at + 1:close]
    options = [m.group(2) for m in _OPTION_RE.finditer(inner)]
    if len(options) != len(_ANY_STRING_RE.findall(inner)):
        raise LedgerError(
            f"{LEDGER}: '{key}' lists a name that is not a plain identifier, so it "
            'would be dropped from the count. Every option must be quoted and match '
            '[A-Za-z_][A-Za-z0-9_]*.'
        )
    surfaces[key] = options
    return close + 1


def _keys_in_source(body: str) -> List[str]:
    """A second, independent reading of which surfaces the literal declares."""
    return [
        m.group(2) if m.group(2) is not None else m.group(3)
        for m in _KEY_RE.finditer(body)
    ]


def _verify_parse(body: str, surfaces: Dict[str, List[str]], iterated: Iterable[str]) -> None:
    """Refuse to report a surface as gone when the ledger still declares it.

    Two cross-checks, because the failure this exists to stop is silent: a
    surface that drops out of the parse LOWERS the total, which reads as
    progress and is bankable with --write.

    1. The scanner's keys must match an independently written regex scan of the
       same text.
    2. Every surface the TypeScript iterates with `unhonouredFor('X')` must
       either be parsed or be genuinely absent from the ledger text. Present in
       the text but missing from the parse is a parse failure, never a closure.
    """
    declared = _keys_in_source(body)
    if sorted(declared) != sorted(surfaces):
        lost = sorted(set(declared) - set(surfaces))
        extra = sorted(set(surfaces) - set(declared))
        raise LedgerError(
            f'{LEDGER}: two readings of the ledger disagree. '
            f'Declared but not parsed: {lost or "none"}; parsed but not declared: {extra or "none"}. '
            'A surface that vanishes from the parse would read as options closed.'
        )
    if len(declared) != len(surfaces):  # pragma: no cover - implied by the sort above
        raise LedgerError(f'{LEDGER}: {len(declared)} entries declared, {len(surfaces)} parsed')

    for surface in sorted(set(iterated)):
        if surface in surfaces:
            continue
        # A surface named at a `unhonouredFor('X')` call site may be declared in
        # the ledger with a quoted OR a bare key; both must be searched, or a
        # bare-key surface that dropped from the parse would slip through here.
        quoted = r'([\'"`])' + re.escape(surface) + r'\1\s*:'
        bare = r'(?<![\w$])' + re.escape(surface) + r'\s*:' if re.fullmatch(r'[A-Za-z_$][\w$]*', surface) else None
        if re.search(quoted, body) or (bare and re.search(bare, body)):
            raise LedgerError(
                f"{LEDGER} still declares '{surface}', which the TypeScript iterates with "
                f"unhonouredFor('{surface}'), but the parse did not see it. That would count "
                'its options as closed. Fix the parser, not the number.'
            )


def _iterated_surfaces(sources: Sequence[Tuple[str, str]]) -> List[str]:
    """Surfaces the TypeScript reads back out of the ledger at runtime."""
    found: List[str] = []
    for _, text in sources:
        found += _ITERATES_RE.findall(text)
    return found


def read_ledger(repo_root: Path) -> Behaviour:
    """Parse the ledger and the partial-case call sites out of the sources."""
    ledger_path = repo_root / LEDGER
    if not ledger_path.is_file():
        raise LedgerError(f'{LEDGER} not found; is --repo-root right?')
    body = _strip_comments(_ledger_block(ledger_path.read_text(encoding='utf-8')))

    surfaces = _parse_entries(body)
    if not surfaces:
        # Refuse to report "nothing left to do" because a regex stopped matching.
        raise LedgerError(f'no surfaces parsed from {LEDGER}; the ledger shape changed')

    sources: List[Tuple[str, str]] = []
    src = repo_root / TS_SOURCE
    for path in sorted(src.rglob('*.ts')):
        if path.name == 'parity-notice.ts':
            continue
        sources.append((str(path.relative_to(repo_root).as_posix()), path.read_text(encoding='utf-8')))

    _verify_parse(body, surfaces, _iterated_surfaces(sources))

    partial: List[Dict[str, str]] = []
    for rel, text in sources:
        for surface, option in _PARTIAL_RE.findall(text):
            partial.append({'surface': surface, 'option': option, 'file': rel})
    return Behaviour(surfaces=surfaces, partial=partial)


def render_markdown(b: Behaviour) -> str:
    lines = [
        '# Behaviour Parity: options accepted but not yet acted on',
        '',
        '<!-- Generated by `python -m praisonai._dev.parity.behaviour --write`. Do not edit by hand. -->',
        '',
        '## What this measures',
        '',
        'PARITY.md asks whether a name is exported. SIGNATURE_PARITY.md asks whether a',
        'parameter exists. Both pass for an option that is accepted and then ignored, so',
        'this file counts those: every option the TypeScript SDK takes for Python parity',
        'and does not yet act on. The source is the `UNHONOURED_OPTIONS` ledger in',
        '`src/praisonai-ts/src/utils/parity-notice.ts`, which the surfaces iterate at',
        'runtime, so every option listed here announces itself when it is passed.',
        '',
        'The check is a ratchet: the total may fall, never rise, and `--write` enforces',
        'the same ratchet so a rise cannot be committed without `--allow-growth` and a',
        'reason. What no check can see is whether a row DELETED from the ledger was',
        'really implemented: the ledger is hand-written, so each removal is a claim that',
        'needs a test proving the option changes what the code does.',
        '',
        '## Summary',
        '',
        '| Surface | Options not yet acted on |',
        '|---|---|',
    ]
    for surface in sorted(b.surfaces):
        lines.append(f'| `{surface}` | {len(b.surfaces[surface])} |')
    lines += [
        f'| **Total** | **{b.total}** |',
        '',
        f'Plus {len(b.partial)} options that work for some inputs and announce themselves for the rest.',
        '',
        '## The queue',
        '',
        'Each row is one unit of work: implement it, delete its entry from the ledger,',
        'add a test proving the option changes what the code does, and regenerate.',
        '',
    ]
    for surface in sorted(b.surfaces):
        options = b.surfaces[surface]
        if not options:
            continue
        lines += [f'### `{surface}` ({len(options)})', '']
        lines += [f'- `{option}`' for option in options]
        lines.append('')
    if b.partial:
        lines += ['## Partial', '', '| Surface | Option | Declared in |', '|---|---|---|']
        for row in sorted(b.partial, key=lambda r: (r['surface'], r['option'])):
            lines.append(f"| `{row['surface']}` | `{row['option']}` | `{row['file']}` |")
        lines.append('')
    return '\n'.join(lines)


def render_json(b: Behaviour) -> str:
    payload = {
        'total': b.total,
        'surfaces': {k: sorted(v) for k, v in sorted(b.surfaces.items())},
        'partial': sorted(b.partial, key=lambda r: (r['surface'], r['option'])),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + '\n'


def committed_report(repo_root: Path) -> Optional[Dict]:
    """The report as last committed, or None if it is missing or unreadable."""
    path = repo_root / JSON_OUTPUT
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        int(data['total'])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return data


def committed_total(repo_root: Path) -> Optional[int]:
    data = committed_report(repo_root)
    return None if data is None else int(data['total'])


def _removed_since(previous: Optional[Dict], now: Behaviour) -> List[str]:
    """`Surface.option` entries the ledger has dropped since the last commit."""
    if not previous:
        return []
    before = previous.get('surfaces') or {}
    if not isinstance(before, dict):
        return []
    gone: List[str] = []
    for surface, options in sorted(before.items()):
        current = set(now.surfaces.get(surface, []))
        for option in sorted(options if isinstance(options, list) else []):
            if option not in current:
                gone.append(f'{surface}.{option}')
    return gone


# Deleting an entry from the ledger is a CLAIM that the behaviour was
# implemented, and nothing here can verify it: the ledger is hand-written, and
# every option in it is already named in the TypeScript sources (the signature
# gate requires the parameter to exist) and in some test. Measured, not assumed
# -- see the README's "what this cannot check". So this prints the claim for a
# reviewer instead of pretending to check it.
_REMOVAL_NOTE = (
    'This tool cannot verify that: the ledger is hand-written and the option name '
    'already appears in the sources and tests either way. Each needs a test proving '
    'the option changes what the code does, with a control showing it does not when '
    'the option is absent.'
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument('--write', action='store_true', help='regenerate the report')
    parser.add_argument('--check', action='store_true', help='fail if the report is stale or the total grew')
    parser.add_argument(
        '--allow-growth',
        action='store_true',
        help=(
            'let --write RAISE the committed total. Growth means another option is '
            'accepted and ignored, so it needs a reason in the pull request that '
            'banks it. Lowering the total never needs this flag.'
        ),
    )
    parser.add_argument('--repo-root', type=Path, default=None)
    args = parser.parse_args(argv)

    repo_root = args.repo_root or find_repo_root()
    try:
        b = read_ledger(repo_root)
    except LedgerError as exc:
        print(f'behaviour parity: cannot read the ledger: {exc}', file=sys.stderr)
        return 2
    md, js = render_markdown(b), render_json(b)

    previous = committed_report(repo_root)
    baseline = None if previous is None else int(previous['total'])

    if args.write:
        # The ratchet has to hold here too. This runs on every push to main and
        # auto-commits, so without this a rise reached main by being written
        # rather than by being argued for, and became the new floor.
        if baseline is not None and b.total > baseline and not args.allow_growth:
            print(
                f'behaviour parity: refusing to write. {b.total} options are accepted and not '
                f'acted on, up from the committed {baseline}. Implement the behaviour, or pass '
                '--allow-growth and say in the pull request why another option had to be '
                'accepted before it works.',
                file=sys.stderr,
            )
            return 1
        removed = _removed_since(previous, b)
        (repo_root / MD_OUTPUT).write_text(md, encoding='utf-8')
        (repo_root / JSON_OUTPUT).write_text(js, encoding='utf-8')
        print(f'wrote {MD_OUTPUT} and {JSON_OUTPUT} -- {b.total} options across {len(b.surfaces)} surfaces')
        if removed:
            print(f'\nclaimed closed by this change ({len(removed)}): {", ".join(removed)}')
            print(_REMOVAL_NOTE)
        if baseline is not None and b.total > baseline:
            print(f'\nthe total ROSE from {baseline} to {b.total}, banked with --allow-growth.')
        return 0

    print(f'behaviour parity: {b.total} options not yet acted on, across {len(b.surfaces)} surfaces'
          f'; {len(b.partial)} partial')
    if not args.check:
        print(md)
        return 0

    failures: List[str] = []
    if baseline is None:
        failures.append(f'{JSON_OUTPUT} is missing or unreadable -- run --write and commit it')
    elif b.total > baseline:
        failures.append(
            f'{b.total} options are accepted but not acted on, up from {baseline}. '
            'An option that is accepted and ignored passes the name and signature gates, '
            'so this is the only check that sees it. Implement it, or say why it had to grow.'
        )
    stale = [
        path.relative_to(repo_root)
        for path, content in ((repo_root / MD_OUTPUT, md), (repo_root / JSON_OUTPUT, js))
        if not path.is_file() or path.read_text(encoding='utf-8') != content
    ]
    if stale and baseline is not None and b.total < baseline:
        # Closing an option is the point of this file. Say that first, so the
        # instruction reads as banking progress rather than as a reprimand.
        print(f'\n{baseline - b.total} option(s) closed since the last commit: {baseline} -> {b.total}.')
        removed = _removed_since(previous, b)
        if removed:
            print(f'claimed closed: {", ".join(removed)}')
            print(_REMOVAL_NOTE)
    failures += [f'{rel} is out of date -- run --write and commit the result' for rel in stale]

    if failures:
        print(f'\nFAILURES ({len(failures)}):')
        for f in failures:
            print(f'  - {f}')
        print('behaviour parity: FAILED')
        return 1
    if baseline is not None and b.total < baseline:
        print(f'behaviour parity: OK -- down from {baseline} to {b.total}; run --write to bank it')
    else:
        print('behaviour parity: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
