"""Every outbound fetch of an untrusted URL goes through ``url_safety``.

Class guard for server-side request forgery. The helper
(:func:`praisonaiagents.tools.url_safety.safe_fetch` / ``safe_stream``) resolves
the host once, rejects internal ranges, pins the checked address for the
connection and re-checks every redirect hop. A call that builds its own HTTP
request skips all of that.

This test walks the SDK and, in the monorepo, its sibling packages, and lists
every HTTP call whose URL is not a literal (``requests.*``, ``httpx.*``,
``urlopen``, ``build_opener`` and client constructors). Each one must be vetted
below. A new site fails the test: route it through ``safe_fetch``, or, when the
URL only ever comes from the operator (config, env, CLI flag), a fixed vendor
host or a local service the CLI itself runs, add it to the matching set.

``PENDING`` lists untrusted-URL sites not yet routed through the helper. It may
only shrink: remove an entry when its call site is fixed.
"""
from __future__ import annotations

import ast
import functools
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
_PACKAGES = (
    "praisonai-agents/praisonaiagents",
    "praisonai/praisonai",
    "praisonai-code/praisonai_code",
    "praisonai-bot/praisonai_bot",
    "praisonai-mcp/praisonai_mcp",
    "praisonai-browser/praisonai_browser",
    "praisonai-deploy/praisonai_deploy",
    "praisonai-sandbox/praisonai_sandbox",
    "praisonai-train/praisonai_train",
)
_HELPER = "praisonai-agents/praisonaiagents/tools/url_safety.py"
_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}
_CALLS = {("requests", v) for v in _VERBS} | {("httpx", v) for v in _VERBS}
_CLIENTS = {("httpx", "Client"), ("httpx", "AsyncClient"), ("requests", "Session"), ("aiohttp", "ClientSession")}


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return [node.id] + parts[::-1]
    return None


def _literal_url(node) -> bool:
    """A string literal, or an f-string whose scheme and host are literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        if isinstance(head, ast.Constant) and str(head.value).startswith(("http://", "https://")):
            return "/" in str(head.value).split("://", 1)[1]
    return False


def _url_arg(call: ast.Call, verb: str):
    for kw in call.keywords:
        if kw.arg == "url":
            return kw.value
    index = 1 if verb in ("request", "stream") else 0
    return call.args[index] if len(call.args) > index else None


def _kind(call: ast.Call):
    name = _dotted(call.func)
    if not name:
        return None
    if name[-1] in ("urlopen", "build_opener"):
        return name[-1]
    if len(name) >= 2 and (name[-2], name[-1]) in _CALLS | _CLIENTS:
        return f"{name[-2]}.{name[-1]}"
    return None


def _scan(rel: str, root: Path = _SRC) -> set:
    found = set()
    for file in sorted((root / rel).rglob("*.py")):
        file_rel = file.relative_to(root).as_posix()
        if file_rel == _HELPER:
            continue
        try:
            text = file.read_text(encoding="utf-8")
            if not any(word in text for word in ("requests", "httpx", "urlopen", "build_opener", "aiohttp")):
                continue
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue
        scope = []

        class Visitor(ast.NodeVisitor):
            def _scoped(self, node):
                scope.append(node.name)
                self.generic_visit(node)
                scope.pop()

            visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scoped

            def visit_Call(self, node):
                kind = _kind(node)
                if kind:
                    # A client object's later .get(url) is invisible here, so
                    # the constructor itself is the site to vet.
                    is_client = tuple(kind.split(".")) in _CLIENTS
                    url = None if is_client else _url_arg(node, kind.split(".")[-1])
                    if url is None or not _literal_url(url):
                        found.add(f"{file_rel}::{'.'.join(scope) or '<module>'}::{kind}")
                self.generic_visit(node)

        Visitor().visit(tree)
    return found


# URL comes only from the operator: config, env var, CLI flag or constructor arg.
OPERATOR = frozenset({
    "praisonai-agents/praisonaiagents/decisions/system_one.py::asystem_one::aiohttp.ClientSession",
    "praisonai-agents/praisonaiagents/decisions/system_one.py::system_one::urlopen",
    "praisonai-agents/praisonaiagents/mcp/mcp_http_stream.py::HTTPStreamTransport.__aenter__::aiohttp.ClientSession",
    "praisonai-agents/praisonaiagents/session/api.py::Session._test_remote_connection::requests.get",
    "praisonai-agents/praisonaiagents/session/api.py::Session._test_remote_connection::requests.head",
    "praisonai-agents/praisonaiagents/session/api.py::Session.chat::requests.post",
    "praisonai-agents/praisonaiagents/ui/a2a/client.py::A2AClient._get_session::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_webhook_approval.py::WebhookApproval._http_request::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_webhook_approval.py::WebhookApproval.request_approval::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/gateway/gateway_approval.py::GatewayApprovalBackend._notify::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/scheduler/_standalone_sender.py::_post_json::urlopen",
    "praisonai-code/praisonai_code/cli/configuration/credentials.py::CredentialStore._refresh_oauth_token::requests.post",
    "praisonai-code/praisonai_code/cli/configuration/oauth.py::run_authcode_flow::requests.post",
    "praisonai-code/praisonai_code/cli/configuration/oauth.py::run_device_code_flow::requests.post",
    "praisonai-code/praisonai_code/cli/configuration/resolver.py::ConfigResolver._fetch_managed_url::urlopen",
    "praisonai-code/praisonai_code/cli/features/jobs.py::JobsHandler._get_client::httpx.Client",
    "praisonai-code/praisonai_code/cli/features/jobs.py::JobsHandler.stream::httpx.stream",
    "praisonai-code/praisonai_code/cli/features/n8n.py::N8nHandler._activate_workflow::requests.post",
    "praisonai-code/praisonai_code/cli/features/n8n.py::N8nHandler._create_workflow_via_api::requests.post",
    "praisonai-deploy/praisonai_deploy/api.py::check_api_health::urlopen",
    # `praisonai connect --url`: the operator probes a server URL they typed.
    "praisonai-mcp/praisonai_mcp/connect/probe.py::_verify_url.post::urlopen",
    "praisonai-mcp/praisonai_mcp/mcp_server/auth/oauth.py::OAuthManager._token_request::httpx.AsyncClient",
    "praisonai-mcp/praisonai_mcp/mcp_server/auth/oidc.py::OIDCDiscovery._fetch_config::httpx.AsyncClient",
    "praisonai-train/praisonai_train/data/benchmark.py::_timed_call::urlopen",
    "praisonai-train/praisonai_train/data/generate.py::_call::urlopen",
    "praisonai/praisonai/capabilities/passthrough.py::_get_async_client::httpx.AsyncClient",
    "praisonai/praisonai/capabilities/passthrough.py::_get_sync_client::httpx.Client",
    "praisonai/praisonai/cli/features/endpoints.py::EndpointsHandler._make_request::urlopen",
    "praisonai/praisonai/cli/features/endpoints.py::EndpointsHandler._stream_request::urlopen",
    "praisonai/praisonai/cli/features/tools.py::ToolsHandler.action_add::urlopen",
    "praisonai/praisonai/cli/langfuse_client.py::LangfuseClient.__init__::requests.Session",
    "praisonai/praisonai/endpoints/providers/a2a.py::A2AProvider.invoke_stream::urlopen",
    "praisonai/praisonai/endpoints/providers/a2u.py::A2UProvider.invoke_stream::urlopen",
    "praisonai/praisonai/endpoints/providers/base.py::BaseProvider._make_request::urlopen",
    "praisonai/praisonai/endpoints/providers/recipe.py::RecipeProvider.invoke_stream::urlopen",
    "praisonai/praisonai/flow/client.py::LangflowClient.__init__::requests.Session",
    "praisonai/praisonai/n8n/client.py::N8nClient._get_session::httpx.Client",
    "praisonai/praisonai/push/transports.py::PollingTransport.connect::aiohttp.ClientSession",
    "praisonai/praisonai/recipe/operations.py::JobHandle.client::httpx.Client",
    "praisonai/praisonai/recipe/operations.py::submit_job::httpx.Client",
    "praisonai/praisonai/recipe/registry.py::HttpRegistry._download_file::urlopen",
    "praisonai/praisonai/recipe/registry.py::HttpRegistry._request::urlopen",
    "praisonai/praisonai/recipe/registry.py::HttpRegistry._upload_file::urlopen",
    "praisonai/praisonai/templates/registry.py::TemplateRegistry._make_request::urlopen",
    "praisonai/praisonai/templates/registry.py::TemplateRegistry.http_client::httpx.Client",
})

# Fixed vendor API host held in a variable (GitHub, PyPI, Slack, Discord, ...).
VENDOR = frozenset({
    "praisonai-agents/praisonaiagents/agent/context_agent.py::ContextAgent._get_github_sample_files::urlopen",
    "praisonai-agents/praisonaiagents/agent/context_agent.py::ContextAgent._get_structure_fallback::urlopen",
    "praisonai-agents/praisonaiagents/tools/web_search.py::_search_brave::requests.get",
    "praisonai-bot/praisonai_bot/bots/_discord_approval.py::DiscordApproval._discord_api::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_discord_approval.py::DiscordApproval._update_message::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_discord_approval.py::DiscordApproval.request_approval::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_slack_approval.py::SlackApproval._slack_api::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_slack_approval.py::SlackApproval.request_approval::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_telegram_approval.py::TelegramApproval._telegram_api::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/_telegram_approval.py::TelegramApproval.request_approval::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/discord.py::DiscordBot.probe::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/linear.py::LinearBot.start::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/signal.py::SignalBot.probe::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/signal.py::SignalBot.start::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/slack.py::SlackBot._transcribe_audio::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/slack.py::SlackBot.probe::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/telegram.py::TelegramBot.probe::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/whatsapp.py::WhatsAppBot._start_cloud_mode::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/bots/whatsapp.py::WhatsAppBot._start_web_mode::aiohttp.ClientSession",
    "praisonai-bot/praisonai_bot/scheduler/_standalone_sender.py::_slack_send._send::urlopen",
    "praisonai-code/praisonai_code/cli/commands/github.py::fetch_github_api::urlopen",
    "praisonai-code/praisonai_code/cli/commands/github.py::github_triage::urlopen",
    "praisonai-code/praisonai_code/cli/commands/version.py::version_check::urlopen",
    "praisonai-code/praisonai_code/cli/features/doctor/checks/network_checks.py::check_network_https::urlopen",
    "praisonai-code/praisonai_code/cli/features/package.py::PackageHandler.cmd_search::urlopen",
    "praisonai-code/praisonai_code/cli/features/self_manage.py::get_latest_version::urlopen",
    "praisonai-sandbox/praisonai_sandbox/compute/flyio.py::FlyioCompute._api_request::aiohttp.ClientSession",
})

# A loopback service the CLI itself starts or probes (gateway, Chrome CDP, runtime).
LOCAL = frozenset({
    "praisonai-agents/praisonaiagents/local/discover.py::default_transport::urlopen",
    "praisonai-bot/praisonai_bot/cli/commands/gateway.py::_channel_control::requests.post",
    "praisonai-bot/praisonai_bot/cli/commands/gateway.py::_fetch_gateway::urlopen",
    "praisonai-bot/praisonai_bot/cli/features/gateway.py::GatewayHandler._print_version_skew::urlopen",
    "praisonai-bot/praisonai_bot/cli/features/gateway.py::GatewayHandler.status::urlopen",
    "praisonai-bot/praisonai_bot/gateway/preflight.py::_http_get_json::urlopen",
    "praisonai-bot/praisonai_bot/gateway/preflight.py::_scrape_metrics_counter::urlopen",
    "praisonai-bot/praisonai_bot/gateway/preflight.py::check_gateway_running::urlopen",
    "praisonai-browser/praisonai_browser/benchmark.py::BrowserBenchmark._check_bridge_server::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/benchmark.py::BrowserBenchmark._check_cdp_available::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cdp_agent.py::CDPBrowserAgent._get_targets::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cdp_agent.py::run_hybrid::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cdp_utils.py::_connect_to_page::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cdp_utils.py::get_pages::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::_require_bridge::urlopen",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::capture_screenshot::requests.get",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::chrome_start.check_port::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::chrome_status.check::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::chrome_stop.stop::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::doctor_chrome::requests.get",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::doctor_extension::requests.get",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::doctor_server::requests.get",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::execute_script::requests.get",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::extension_load.check_chrome::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::launch_browser.check_chrome::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::launch_browser.check_server::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::launch_browser.run_goal::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::launch_browser.verify_extension_loaded::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::manage_tabs::requests.get",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::manage_tabs::requests.put",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::navigate_tab::requests.get",
    "praisonai-browser/praisonai_browser/cli/commands/browser.py::reload_extension.do_reload::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/diagnostics.py::check_bridge_server::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/diagnostics.py::check_chrome_cdp::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/diagnostics.py::check_extension_loaded::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/launcher.py::BrowserLauncher._run_async.check_existing_connection::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/launcher.py::BrowserLauncher._run_async.wait_for_extension::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/server.py::run_browser_agent_with_progress::aiohttp.ClientSession",
    "praisonai-browser/praisonai_browser/server.py::test_extension_mode::aiohttp.ClientSession",
    "praisonai-code/praisonai_code/cli/commands/up.py::ServiceManager.wait_for_service::requests.get",
    "praisonai-code/praisonai_code/cli/commands/up.py::up_status::requests.get",
    "praisonai-code/praisonai_code/cli/features/doctor/checks/serve_checks.py::check_discovery_endpoint::urlopen",
    "praisonai-code/praisonai_code/cli/features/doctor/checks/serve_checks.py::check_server_connectivity::urlopen",
    "praisonai-code/praisonai_code/llm/local_detect.py::_get_json::urlopen",
    "praisonai-code/praisonai_code/runtime/client.py::RuntimeClient._post::urlopen",
    "praisonai-code/praisonai_code/runtime/client.py::RuntimeClient.attach::urlopen",
    "praisonai-train/praisonai_train/train/_llamacpp.py::_server_ready::urlopen",
    "praisonai-train/praisonai_train/train/_ollama.py::_ollama_ready::urlopen",
})

# Untrusted URL (model, user, fetched content, remote metadata) not yet on the
# helper. Follow-up PRs move these to safe_fetch; this set may only shrink.
PENDING = frozenset({
})

VETTED = OPERATOR | VENDOR | LOCAL | PENDING


def _present_packages():
    return [p for p in _PACKAGES if (_SRC / p).is_dir()]


@functools.lru_cache(maxsize=1)
def _found() -> frozenset:
    return frozenset().union(*(_scan(p) for p in _present_packages()))


def test_every_outbound_fetch_site_is_vetted_or_uses_the_helper():
    unvetted = sorted(_found() - VETTED)
    assert not unvetted, (
        "Outbound HTTP call on a non-literal URL outside url_safety. Use "
        "praisonaiagents.tools.url_safety.safe_fetch (or safe_stream), or, if "
        "the URL is operator-only / a fixed vendor host / a local service, add "
        "it to the matching set in this file:\n  " + "\n  ".join(unvetted)
    )


def test_vetted_sets_hold_no_stale_entries():
    """Keeps the ratchet tight: a fixed or removed site must leave the list."""
    present = _present_packages()
    expected = {s for s in VETTED if any(s.startswith(p) for p in present)}
    stale = sorted(expected - _found())
    assert not stale, "Remove these entries; the call site is gone:\n  " + "\n  ".join(stale)


def test_no_untrusted_fetch_is_pending():
    """Every untrusted-URL site is on the helper; a new one may not wait here."""
    assert not PENDING, sorted(PENDING)


def test_vetted_sets_do_not_overlap():
    sets = (OPERATOR, VENDOR, LOCAL, PENDING)
    assert sum(len(s) for s in sets) == len(VETTED)


def test_scanner_flags_a_direct_fetch(tmp_path):
    """Control probe: the scanner sees each call shape it is meant to catch."""
    pkg = tmp_path / "praisonai-agents" / "praisonaiagents"
    pkg.mkdir(parents=True)
    (pkg / "probe.py").write_text(
        "import requests, httpx, urllib.request\n"
        "def a(url): requests.get(url)\n"
        "def b(url): httpx.stream('GET', url)\n"
        "def c(url): urllib.request.urlopen(url)\n"
        "def d(): httpx.Client()\n"
        "def e(): requests.get('https://api.example.com/v1')\n"
        "def f(q): requests.get(f'https://api.example.com/v1?q={q}')\n"
    )
    found = _scan("praisonai-agents/praisonaiagents", root=tmp_path)
    names = {s.split("::")[1] for s in found}
    assert names == {"a", "b", "c", "d"}
