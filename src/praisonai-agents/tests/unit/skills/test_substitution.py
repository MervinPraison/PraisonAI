"""Tests for skill argument/context substitution."""

from praisonaiagents.skills.substitution import render_skill_body


class TestArgumentsPlaceholder:
    def test_arguments_full_string(self):
        body = "Deploy $ARGUMENTS now."
        out = render_skill_body(body, raw_args="staging prod")
        assert out == "Deploy staging prod now."

    def test_arguments_missing_appends_footer(self):
        body = "Do the thing."
        out = render_skill_body(body, raw_args="foo bar")
        assert out.startswith("Do the thing.")
        assert "ARGUMENTS: foo bar" in out

    def test_no_args_leaves_body(self):
        body = "Hello."
        out = render_skill_body(body, raw_args="")
        assert out == "Hello."


class TestIndexedArguments:
    def test_indexed_arguments_bracket(self):
        body = "Migrate $ARGUMENTS[0] from $ARGUMENTS[1] to $ARGUMENTS[2]."
        out = render_skill_body(body, raw_args="SearchBar React Vue")
        assert out == "Migrate SearchBar from React to Vue."

    def test_indexed_shorthand(self):
        body = "Hello $0, meet $1."
        out = render_skill_body(body, raw_args="Alice Bob")
        assert out == "Hello Alice, meet Bob."

    def test_quoted_arg_treated_as_single(self):
        body = "Run $0."
        out = render_skill_body(body, raw_args='"hello world"')
        assert out == "Run hello world."

    def test_missing_indexed_becomes_empty(self):
        body = "x=$0 y=$1 z=$2"
        out = render_skill_body(body, raw_args="only")
        assert out == "x=only y= z="


class TestContextVariables:
    def test_skill_dir_substitution(self):
        body = "cd ${PRAISON_SKILL_DIR}"
        out = render_skill_body(body, raw_args="", skill_dir="/tmp/sk")
        assert out == "cd /tmp/sk"

    def test_session_id_substitution(self):
        body = "log: ${PRAISON_SESSION_ID}"
        out = render_skill_body(body, raw_args="", session_id="sess-42")
        assert out == "log: sess-42"

    def test_claude_aliases_supported(self):
        body = "dir=${CLAUDE_SKILL_DIR} sid=${CLAUDE_SESSION_ID}"
        out = render_skill_body(body, raw_args="", skill_dir="/s", session_id="S1")
        assert out == "dir=/s sid=S1"

    def test_missing_context_leaves_placeholder(self):
        body = "x=${PRAISON_SKILL_DIR}"
        out = render_skill_body(body, raw_args="")
        # Unset -> empty
        assert out == "x="
