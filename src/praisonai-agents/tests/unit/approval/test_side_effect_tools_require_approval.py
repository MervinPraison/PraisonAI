"""Guard: every built-in tool with an outside effect requires approval.

Enumerates every public callable defined in each module named by
``praisonaiagents.tools.TOOL_MAPPINGS`` and requires each one to be classified
here. A new tool fails this test until it is either approval-gated or listed
as exempt with a reason, so a new side-effect tool cannot ship ungated.
"""
import importlib
import inspect

import pytest

import praisonaiagents.tools as tools_pkg
from praisonaiagents.approval import get_approval_registry
from praisonaiagents.approval.registry import PERMISSION_PRESETS

# Tools that change state outside the agent: send or publish data, mutate a
# mailbox or remote service, write or delete files, run code, or queue future
# runs. Each must be approval-gated by default.
REQUIRES_APPROVAL = {
    # files and code
    "write_file", "edit_file", "apply_patch", "delete_file", "move_file",
    "copy_file", "download_file", "ast_grep_rewrite",
    "execute_command", "kill_process", "execute_code", "execute_code_with_tools",
    "run_skill_script", "skill_manage", "todo_add", "todo_update",
    # git egress
    "github_create_branch", "github_commit_and_push", "github_create_pull_request",
    # email
    "send_email", "reply_email", "forward_email", "send_draft", "smtp_send_email",
    "draft_email", "smtp_draft_email", "archive_email", "smtp_archive_email",
    "create_inbox",
    # messaging
    "send_message", "ask_conversation",
    # scheduled future runs
    "schedule_add", "schedule_update", "schedule_remove", "schedule_pause",
    "schedule_resume",
    # already gated web fetchers
    "crawl", "scrape_page",
    # already gated (low) reader
    "read_skill_file",
}

_READ = "read-only: returns data, changes nothing"
_HELPER = "not an agent tool: factory, config or helper"
EXEMPT = {
    # read-only search / retrieval
    **{n: _READ for n in (
        "ast_grep_scan", "ast_grep_search", "read_file", "list_files",
        "get_file_info", "search_files", "glob", "grep",
        "list_emails", "read_email", "search_emails", "list_inboxes",
        "smtp_read_inbox", "smtp_search_inbox",
        "duckduckgo", "internet_search", "searxng", "searxng_search",
        "exa", "exa_search", "exa_search_async", "exa_search_contents",
        "exa_search_contents_async", "exa_find_similar", "exa_answer",
        "exa_answer_async", "tavily", "tavily_search", "tavily_search_async",
        "tavily_extract", "tavily_extract_async", "tavily_crawl", "tavily_map",
        "ydc", "ydc_search", "ydc_contents", "ydc_news", "ydc_images",
        "crawl4ai", "crawl4ai_sync", "crawl4ai_many", "crawl4ai_extract",
        "crawl4ai_extract_sync", "crawl4ai_llm_extract", "crawl_web",
        "web_crawl", "search_web", "extract_links", "extract_text",
        "jira_get_issue_info", "jira_search_issues", "jira_watch_issue",
        "jira_watch_project", "lsp_definition", "lsp_references", "lsp_hover",
        "lsp_document_symbols", "lsp_workspace_symbols", "lsp_implementations",
        "lsp_incoming_calls", "lsp_outgoing_calls", "gateway_status",
        "session_search", "search_memory", "search_learning", "schedule_list",
        "todo_list", "list_skill_scripts", "skills_list", "skill_view",
        "list_processes", "get_command_output", "get_system_info",
        "analyze_code", "format_code", "lint_code", "disassemble_code",
        "computer_screenshot", "computer_screen_size",
    )},
    "clarify": "asks the user a question in the current conversation",
    "store_memory": "the agent's own memory store",
    "store_learning": "the agent's own learning store",
    "stop_command": "stops a background command this agent started",
    **{n: "own fail-closed gate: refused unless set_computer_approval is set"
       for n in ("computer_click", "computer_key", "computer_move",
                 "computer_scroll", "computer_type")},
    **{n: _HELPER for n in (
        "is_ast_grep_available", "get_ast_grep_tools", "set_clarify_handler",
        "reset_clarify_handler", "create_cli_clarify_handler",
        "create_bot_clarify_handler", "set_computer_approval",
        "create_edit_tools", "parse_email_list", "create_file_tools",
        "jira_tools", "build_code_execution_tools", "set_store", "get_store",
        "get_active_session_store", "create_session_tools", "find_shell_syntax",
        "build_subprocess_env", "create_skill_tools", "create_todo_tools",
        "get_llm", "get_available_crawl_providers", "get_available_providers",
    )},
}


def _builtin_tool_names():
    names = set()
    for module_path in sorted({m for m, _ in tools_pkg.TOOL_MAPPINGS.values()}):
        module = importlib.import_module(module_path, "praisonaiagents.tools")
        for name, obj in vars(module).items():
            if name.startswith("_") or inspect.isclass(obj) or not callable(obj):
                continue
            if getattr(obj, "__module__", None) == module.__name__:
                names.add(name)
    return names


def test_every_builtin_tool_is_classified():
    found = _builtin_tool_names()
    unclassified = found - REQUIRES_APPROVAL - set(EXEMPT)
    assert not unclassified, (
        f"Classify these tools: add them to REQUIRES_APPROVAL (and gate them) "
        f"or to EXEMPT with a reason: {sorted(unclassified)}"
    )
    assert not REQUIRES_APPROVAL & set(EXEMPT)
    stale = (REQUIRES_APPROVAL | set(EXEMPT)) - found
    assert not stale, f"Remove entries for tools that no longer exist: {sorted(stale)}"


@pytest.mark.parametrize("name", sorted(REQUIRES_APPROVAL))
def test_side_effect_tool_requires_approval(name):
    _builtin_tool_names()  # import every tool module so decorators register
    assert get_approval_registry().is_required(name), f"{name} is not approval-gated"


@pytest.mark.parametrize("name", ["send_email", "smtp_send_email", "send_message",
                                  "schedule_add", "execute_code_with_tools"])
def test_safe_presets_block_outside_effect_tools(name):
    for preset in ("safe", "read_only"):
        assert name in PERMISSION_PRESETS[preset]
