"""Scores are comparable only when the setup did not change.

Nothing stopped today's numbers being compared against a run made with a
different model, prompt or tool set -- and that comparison looks perfectly
normal, which is what makes it dangerous: the graph moves and the cause is
invisible.
"""
import pytest

from praisonaiagents.eval.fingerprint import (
    FINGERPRINT_VERSION,
    FingerprintMismatch,
    assert_comparable,
    compare_fingerprints,
    fingerprint_parts,
    run_fingerprint,
)


class TestStability:
    def test_the_same_setup_fingerprints_the_same(self):
        a = run_fingerprint(model="gpt-4o", prompt="be helpful", tools=["search"])
        b = run_fingerprint(model="gpt-4o", prompt="be helpful", tools=["search"])
        assert a == b

    def test_reordering_tools_is_the_same_setup(self):
        """Control: tool ORDER is not part of what a score means."""
        a = run_fingerprint(tools=["search", "calc"])
        b = run_fingerprint(tools=["calc", "search"])
        assert a == b

    def test_it_is_versioned(self):
        assert run_fingerprint(model="gpt-4o").startswith(f"{FINGERPRINT_VERSION}:")


class TestWhatChangesAScore:
    @pytest.mark.parametrize("changed", [
        {"model": "gpt-4o-mini"},
        {"prompt": "be terse"},
        {"tools": ["search", "browse"]},
        {"evaluators": ["AccuracyEvaluator"]},
    ])
    def test_a_changed_setup_fingerprints_differently(self, changed):
        base = dict(model="gpt-4o", prompt="be helpful", tools=["search"], evaluators=[])
        assert run_fingerprint(**base) != run_fingerprint(**{**base, **changed})


class TestComparisonGuard:
    def test_mismatched_runs_are_refused(self):
        a = run_fingerprint(model="gpt-4o")
        b = run_fingerprint(model="gpt-4o-mini")
        with pytest.raises(FingerprintMismatch):
            assert_comparable(a, b)

    def test_control_matching_runs_are_allowed(self):
        a = run_fingerprint(model="gpt-4o")
        assert_comparable(a, run_fingerprint(model="gpt-4o"))  # must not raise
        assert compare_fingerprints(a, a) is True

    def test_a_missing_fingerprint_is_not_assumed_comparable(self):
        """An unstamped run is unknown, not equal -- the dangerous default."""
        assert compare_fingerprints("", "") is False
        with pytest.raises(FingerprintMismatch):
            assert_comparable("", "")


class TestPrivacy:
    def test_the_prompt_text_is_hashed_not_stored(self):
        """A fingerprint is written to result files, so it must not carry data."""
        secret = "customer 4111-1111-1111-1111 wants a refund"
        parts = fingerprint_parts(prompt=secret)
        assert secret not in str(parts)
        assert parts["prompt"] and parts["prompt"] != secret


class TestPackageExports:
    def test_fingerprint_api_is_publicly_exported(self):
        """The guard is useless if callers cannot import it -- ``import *``,
        ``dir()`` and tab-completion must all surface it."""
        import praisonaiagents.eval as pkg

        for name in (
            "FINGERPRINT_VERSION",
            "run_fingerprint",
            "fingerprint_parts",
            "compare_fingerprints",
            "assert_comparable",
            "FingerprintMismatch",
        ):
            assert name in pkg.__all__, f"{name} missing from __all__"
            assert getattr(pkg, name) is not None
            assert name in dir(pkg), f"{name} missing from dir()"

    def test_lazy_import_map_has_no_duplicate_keys(self):
        """A duplicated lazy entry silently shadows the earlier one -- assert the
        map is defined once per name."""
        import ast
        import praisonaiagents.eval as pkg

        src = open(pkg.__file__).read()
        module = ast.parse(src)
        for node in ast.walk(module):
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "_LAZY_IMPORTS" for t in node.targets
            ):
                keys = [k.value for k in node.value.keys]
                assert len(keys) == len(set(keys)), (
                    f"duplicate keys: {sorted({k for k in keys if keys.count(k) > 1})}"
                )


class TestSuiteIntegration:
    def test_a_suite_result_carries_its_fingerprint(self):
        from praisonaiagents.eval.suite import EvalSuite

        class _Stub:
            name = "stub"
            def evaluate(self, *a, **k):
                return {"score": 1.0, "success": True}

        result = EvalSuite(evaluators=[_Stub()], name="demo").run(print_summary=False)
        assert result.fingerprint.startswith(FINGERPRINT_VERSION)
        assert result.summary["fingerprint"] == result.fingerprint
