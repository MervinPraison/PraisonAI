"""Focused, network-free tests for the dependency-free HTML->Markdown path."""

from praisonaiagents.tools.web_crawl_tools import _html_to_markdown


def test_headings_and_title():
    md, title = _html_to_markdown(
        "<html><head><title>Docs</title></head>"
        "<body><h1>Top</h1><h2>Sub</h2></body></html>"
    )
    assert title == "Docs"
    assert "# Top" in md
    assert "## Sub" in md


def test_scripts_and_styles_dropped():
    md, _ = _html_to_markdown(
        "<body><script>evil()</script><style>.x{}</style><p>Kept</p></body>"
    )
    assert "evil()" not in md
    assert ".x{}" not in md
    assert "Kept" in md


def test_unordered_and_ordered_lists():
    md, _ = _html_to_markdown(
        "<ul><li>alpha</li><li>beta</li></ul>"
        "<ol><li>one</li><li>two</li></ol>"
    )
    assert "- alpha" in md
    assert "- beta" in md
    assert "1. one" in md
    assert "2. two" in md


def test_paragraph_inside_list_item_stays_on_marker_line():
    md, _ = _html_to_markdown("<ul><li><p>Item text</p></li></ul>")
    # The bullet marker must not be separated from its text by blank lines.
    assert "- Item text" in md


def test_link_relative_target_resolved_against_base():
    md, _ = _html_to_markdown(
        '<a href="/about">About</a>', base_url="https://example.com/docs/"
    )
    assert "[About](https://example.com/about)" in md


def test_link_without_href_keeps_plain_text():
    md, _ = _html_to_markdown("<a>plain</a>")
    assert "plain" in md
    assert "[plain]" not in md


def test_link_with_paren_in_href_is_escaped():
    md, _ = _html_to_markdown('<a href="https://e.com/a(b)c">L</a>')
    # Unescaped ")" would prematurely terminate the Markdown link target.
    assert ")" not in md.split("](", 1)[1].split(")", 1)[0] if "](" in md else True
    assert "%28" in md and "%29" in md


def test_code_fence_grows_beyond_inner_backticks():
    html = "<pre><code>```\nnested\n```</code></pre>"
    md, _ = _html_to_markdown(html)
    # Fence must be longer than the 3-backtick run inside so it doesn't close early.
    assert "````" in md
    assert "nested" in md


def test_code_block_whitespace_preserved():
    html = "<pre>line1\n    indented   \n\n\n\nline2</pre>"
    md, _ = _html_to_markdown(html)
    # Whitespace-sensitive content inside the fence must survive cleanup.
    assert "    indented   " in md
    assert "\n\n\n\n" in md


def test_inline_code_with_backtick_uses_longer_delim():
    md, _ = _html_to_markdown("<p>Use <code>a`b</code> here</p>")
    assert "``" in md
    assert "a`b" in md


def test_malformed_html_does_not_raise():
    md, title = _html_to_markdown("<h1>Unclosed<p>text<ul><li>x")
    assert isinstance(md, str)
    assert isinstance(title, str)
