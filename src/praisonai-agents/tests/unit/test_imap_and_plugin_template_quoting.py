"""Caller-supplied text must not change the IMAP command or the generated plugin file.

IMAP: every SEARCH value goes through ``_imap_quote`` and is passed as its own
argument. Plugin template: every header value goes through ``_header_value``.
The guard tests list every caller so new code cannot reopen the gap.
"""
import ast
import inspect
from pathlib import Path
from unittest import mock

import pytest

from praisonaiagents.tools import email_tools
from praisonaiagents.plugins import discovery


class _FakeIMAP:
    def __init__(self):
        self.searches = []

    def search(self, charset, *criteria):
        self.searches.append(criteria)
        return "OK", [b""]

    def logout(self):
        pass


def _run(func, *args):
    fake = _FakeIMAP()
    with mock.patch.object(email_tools, "_imap_connect", return_value=(fake, "me@example.com")):
        result = func(*args)
    return fake, result


def _tokens(criteria):
    """Split what imaplib sends (arguments joined by spaces) the way a server does."""
    wire, out, i = " ".join(criteria), [], 0
    while i < len(wire):
        if wire[i] == " ":
            i += 1
        elif wire[i] == '"':
            j, buf = i + 1, ""
            while wire[j] != '"':
                if wire[j] == "\\":
                    j += 1
                buf += wire[j]
                j += 1
            out.append(buf)
            i = j + 1
        else:
            j = wire.find(" ", i)
            j = len(wire) if j < 0 else j
            out.append(wire[i:j])
            i = j
    return out


INJECTED_ID = 'x@y.com" OR ALL "'


@pytest.mark.parametrize("func", [
    email_tools._smtp_read_email,
    email_tools._smtp_archive_email,
])
def test_message_id_stays_one_quoted_argument(func):
    fake, _ = _run(func, INJECTED_ID)
    (criteria,) = fake.searches
    assert criteria[:2] == ("HEADER", "Message-ID")
    assert len(criteria) == 3
    assert criteria[2] == '"<x@y.com\\" OR ALL \\">"'
    assert _tokens(criteria) == ["HEADER", "Message-ID", '<x@y.com" OR ALL ">']


def test_reply_message_id_stays_one_quoted_argument():
    fake, _ = _run(email_tools._smtp_reply_email, INJECTED_ID, "hi")
    (criteria,) = fake.searches
    assert criteria == ("HEADER", "Message-ID", '"<x@y.com\\" OR ALL \\">"')


@pytest.mark.parametrize("func,args", [
    (email_tools._smtp_read_email, ("a@b\r\nA1 DELETE INBOX",)),
    (email_tools._smtp_archive_email, ("a@b\nX",)),
    (email_tools._smtp_reply_email, ("a@b\r\nX", "body")),
    (email_tools._smtp_search_emails, ("q\r\nA1 LOGOUT",)),
])
def test_line_breaks_never_reach_the_server(func, args):
    fake, result = _run(func, *args)
    assert fake.searches == []
    assert "Invalid IMAP search value" in result


def test_search_terms_are_quoted_and_escaped():
    fake, _ = _run(email_tools._smtp_search_emails, 'say "hi"\\', "a@b.c", "subj")
    (criteria,) = fake.searches
    assert criteria == ("FROM", '"a@b.c"', "SUBJECT", '"subj"', "TEXT", '"say \\"hi\\"\\\\"')
    assert _tokens(criteria) == ["FROM", "a@b.c", "SUBJECT", "subj", "TEXT", 'say "hi"\\']


def test_search_without_terms_uses_all():
    fake, _ = _run(email_tools._smtp_search_emails)
    assert fake.searches == [("ALL",)]


# --- guard: every IMAP search in the repo quotes through _imap_quote ------------

_REPO_SRC = Path(__file__).resolve().parents[3]
IMAP_MODULES = [
    _REPO_SRC / "praisonai-agents" / "praisonaiagents" / "tools" / "email_tools.py",
    _REPO_SRC / "praisonai-bot" / "praisonai_bot" / "bots" / "email.py",
]
# Every function that issues an IMAP SEARCH (update when adding one).
SEARCH_CALLERS = {
    "email_tools.py": {"_smtp_list_emails", "_smtp_read_email", "_smtp_reply_email",
                       "_smtp_search_emails", "_smtp_archive_email"},
    "email.py": {"_check_new_emails"},
}


def _is_safe_arg(node):
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_imap_quote":
        return True
    if isinstance(node, (ast.List, ast.Tuple)):
        return all(_is_safe_arg(e) for e in node.elts)
    if isinstance(node, ast.BoolOp):  # criteria or ["ALL"]
        return all(_is_safe_arg(v) for v in node.values)
    if isinstance(node, ast.Starred):
        return _is_safe_arg(node.value)
    return isinstance(node, ast.Name) and node.id == "criteria"


@pytest.mark.parametrize("path", IMAP_MODULES, ids=lambda p: p.name)
def test_guard_every_imap_search_argument_is_constant_or_quoted(path):
    if not path.exists():
        pytest.skip(f"{path} not in this checkout")
    tree = ast.parse(path.read_text())
    callers = set()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "search" \
                    and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value is None:
                callers.add(func.name)
                for arg in node.args[1:]:
                    assert _is_safe_arg(arg), f"{path.name}:{node.lineno} unquoted IMAP search value"
            # Anything added to ``criteria`` must be constant or quoted too.
            if isinstance(node, ast.AugAssign) and getattr(node.target, "id", None) == "criteria":
                assert _is_safe_arg(node.value), f"{path.name}:{node.lineno}"
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "append" \
                    and getattr(node.func.value, "id", None) == "criteria":
                assert all(_is_safe_arg(a) for a in node.args), f"{path.name}:{node.lineno}"
    # A new search site must be added to SEARCH_CALLERS after review.
    assert callers == SEARCH_CALLERS[path.name]


# --- plugin template ----------------------------------------------------------

def _compile_header(source):
    tree = ast.parse(source)
    return ast.get_docstring(tree, clean=False), [type(n).__name__ for n in tree.body]


def test_plugin_template_value_cannot_close_the_docstring():
    payload = 'x"""\nimport os; os.system("id")\n"""'
    with pytest.raises(ValueError, match="single line"):
        discovery.get_plugin_template("p", payload)


def test_plugin_template_quotes_stay_inside_the_header():
    source = discovery.get_plugin_template('n"""', 'd"""; import os #', 'a\\')
    doc, body = _compile_header(source)
    assert body[0] == "Expr" and "Import" not in body[:2]
    assert 'Plugin Name: n"""' in doc
    assert 'Description: d"""; import os #' in doc
    assert "Author: a\\" in doc
    exec(compile(source, "plugin.py", "exec"), {"__name__": "plugin_test"})


def test_plugin_template_defaults_unchanged():
    source = discovery.get_plugin_template("weather")
    assert "Plugin Name: weather\nDescription: A PraisonAI plugin\n" in source
    assert "Author: Your Name\n" in source


def test_guard_every_template_value_goes_through_header_value():
    src = inspect.getsource(discovery.get_plugin_template)
    for field in ("name", "description", "author"):
        assert f'{field} = _header_value(' in src
