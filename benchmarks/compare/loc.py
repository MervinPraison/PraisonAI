"""Count code lines and tokens of a Python file with ``tokenize``.

Blank lines, comments and docstrings (bare string statements) are excluded, as
is every logical line tagged with a ``# bench:config`` comment (the shared
endpoint/model configuration). A line counts when it holds at least one code
token, so the count is physical code lines after ``ruff format``.
"""

from __future__ import annotations

import io
import sys
import tokenize

MARKER = "bench:config"
_SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
         tokenize.ENCODING, tokenize.ENDMARKER}


def count(source: str) -> dict:
    lines: set[int] = set()
    tokens = 0
    logical: list[tokenize.TokenInfo] = []
    tagged = False
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and MARKER in tok.string:
            tagged = True
        if tok.type not in _SKIP:
            logical.append(tok)
        if tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            bare_string = len(logical) == 1 and logical[0].type == tokenize.STRING
            if logical and not bare_string and not tagged:
                tokens += len(logical)
                for t in logical:
                    lines.update(range(t.start[0], t.end[0] + 1))
            logical, tagged = [], False
    return {"lines": len(lines), "tokens": tokens}


if __name__ == "__main__":
    for path in sys.argv[1:]:
        with open(path) as f:
            print(path, count(f.read()))
