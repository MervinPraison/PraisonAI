"""A cap on tests that read source text instead of running it.

An adversarial audit ran 16 mutations against this suite. **Eight survived all
408 tests**, and every survivor was covered only by an assertion of this shape:

    src = inspect.getsource(some_function)
    assert "the_thing_i_want" in src

That passes whether or not the code does anything, because the string is still
in the file when the branch around it is disabled. Three separate times in this
package a test matched an explanatory *comment* rather than the code it
described — in Python, in CSS, and in a YAML workflow.

The rule this file enforces is not "never inspect source". Ordering constraints
("X must happen before Y") are legitimately structural and there is no other
way to state them. The rule is that the count must not grow: a new one needs a
deliberate bump here, which is the moment to ask whether the thing could be
extracted and called instead — as `resolve_mask_setting`,
`decide_masking`, `_accepted_config_fields` and `rewards.require` all were,
each after a mutation proved its source-text test worthless.
"""

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent

# Measured at the time of writing. Lower this as tests are converted; raising it
# is a decision, not an accident.
# Raised deliberately from 14 when the audit-fixes PR landed. One of its four
# was convertible and was converted (_launch_script returns the command, so
# there was no reason to read its source); the rest are ordering constraints,
# which is the case this cap exists to allow.
MAX_SOURCE_TEXT_ASSERTIONS = 18


def _code_only(source):
    """Source with comments and string literals removed."""
    import io
    import tokenize

    kept = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return source
    return " ".join(kept)


def _counts():
    found = {}
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        n = len(re.findall(r"inspect\s*\.\s*getsource", _code_only(path.read_text())))
        if n:
            found[path.name] = n
    return found


def test_source_text_assertions_do_not_grow():
    counts = _counts()
    total = sum(counts.values())
    assert total <= MAX_SOURCE_TEXT_ASSERTIONS, (
        f"{total} source-text assertions, cap is {MAX_SOURCE_TEXT_ASSERTIONS}.\n"
        f"{counts}\n"
        "Extract the logic and call it instead, or raise the cap deliberately."
    )


def test_no_test_reimplements_the_logic_it_tests():
    """A test holding a copy of the code cannot detect that code changing.

    `test_response_masking.py` defined `_auto_use_mask()` as a mirror of
    train_model's expression. Reverting the real line to the pre-fix behaviour
    left the whole suite green — the one defect that PR existed to fix was
    undetectable by its own test file.
    """
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue      # this file names the pattern in order to ban it
        # Comments and docstrings stripped. Without this the guard matched the
        # comment in test_response_masking.py that EXPLAINS the removed copy --
        # the fourth time in this session an assertion read prose instead of
        # code, which is the whole reason this file exists.
        text = _code_only(path.read_text())
        assert "_auto_use_mask" not in text, (
            f"{path.name} reimplements masking logic instead of calling "
            "trainer.resolve_mask_setting")


def test_the_extracted_helpers_are_importable_and_callable():
    """Each of these exists because a source-text test failed to catch a bug.

    If one is inlined again, its test silently goes back to proving nothing.
    """
    from praisonai_train import rewards
    from praisonai_train.train.llm import trainer

    for module, name in (
        (trainer, "resolve_mask_setting"),
        (trainer, "decide_masking"),
        (trainer, "resolve_response_markers"),
        (trainer, "is_out_of_memory"),
        (rewards, "require"),
        (rewards, "resolve_all"),
    ):
        fn = getattr(module, name, None)
        assert callable(fn), (
            f"{module.__name__}.{name} is gone; whatever tested it is now "
            "asserting on source text again")
