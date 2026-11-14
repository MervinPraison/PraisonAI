"""configure_host(pages=...) must not take away aiui's theme choice.

``praisonai claw`` (claw/default_app.py) and ``build_host_app(pages=[...])``
pass a page whitelist. configure_host handed it straight to
``aiui.set_pages``, which hides every built-in page not listed, including
aiui's Theme page (``theme-picker``). The hosted dashboard then had no Theme
page and no palette entry for it, so it was stuck in dark mode.
"""

from __future__ import annotations

from starlette.testclient import TestClient


def _page_ids(client: TestClient) -> list[str]:
    data = client.get("/api/pages").json()
    pages = data.get("pages", data) if isinstance(data, dict) else data
    return [p["id"] for p in pages]


def test_whitelist_keeps_the_theme_page(isolated_host):
    isolated_host.configure_host(pages=["chat", "usage"])
    ids = _page_ids(TestClient(isolated_host.create_host_app()))
    assert "theme-picker" in ids
    assert "chat" in ids and "usage" in ids
    # The whitelist still hides what it does not list.
    assert "sessions" not in ids


def test_claw_style_whitelist_shows_the_theme_page(isolated_host):
    import praisonaiui.server as srv

    isolated_host.configure_host(pages=["chat", "config", "logs", "debug"])
    assert "theme-picker" in srv._enabled_pages


def test_theme_page_is_not_duplicated():
    from praisonai_bot.integration.host_app import _whitelist_with_theme_page

    assert _whitelist_with_theme_page(["chat", "theme-picker"]) == ["chat", "theme-picker"]
    assert _whitelist_with_theme_page(("chat",)) == ["chat", "theme-picker"]
    assert _whitelist_with_theme_page([]) == ["theme-picker"]


def test_no_whitelist_leaves_aiui_defaults(isolated_host):
    import praisonaiui.server as srv

    isolated_host.configure_host()
    assert srv._enabled_pages is None
