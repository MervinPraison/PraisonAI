/**
 * Settings as data -- GENERATED. Do not edit.
 *
 * The shipped copy is the block inlined in ui/index.html. Regenerate with
 * `node tools/sync-registry.mjs`; `--check` verifies without writing.
 */
export const SECTIONS = [
  { id: "general",    label: "General",    icon: "⚙" },
  { id: "model",      label: "Models",     icon: "◈" },
  { id: "chat",       label: "Chat",       icon: "◇" },
  { id: "appearance", label: "Appearance", icon: "◐" },
  { id: "safety",     label: "Safety",     icon: "⚿" },
  { id: "data",       label: "Data",       icon: "▤" },
  { id: "integrations", label: "Integrations", icon: "⧉" },
  { id: "about",      label: "About",      icon: "ⓘ" },
];

const clampNum = (min, max) => (v) =>
  v === "" || v === null ? null
  : Number.isNaN(Number(v)) ? "Must be a number"
  : Number(v) < min ? `Must be at least ${min}`
  : Number(v) > max ? `Must be at most ${max}` : null;

const SETTINGS = [
  // ---- Models -------------------------------------------------------------
  { key: "model", section: "model", label: "Default model",
    description: "Any OpenAI-compatible model id. New chats use this. A provider-prefixed id (anthropic/…, gemini/…, ollama/…) routes through litellm to that provider — set its API key in the environment, or run Ollama locally. For an OpenAI-compatible endpoint instead, set a Base URL and use that endpoint’s bare model id.",
    keywords: ["llm", "gpt", "claude", "provider"],
    control: { kind: "combobox", suggestions: [
      "gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini",
        "anthropic/claude-sonnet-4-20250514", "gemini/gemini-2.0-flash",
        "ollama/llama3.2",
    ]},
    default: "gpt-4o-mini" },

  { key: "temperature", section: "model", label: "Temperature",
    description: "Higher is more varied. 0 is nearly deterministic.",
    control: { kind: "slider", min: 0, max: 2, step: 0.05 },
    default: 0.7, validate: clampNum(0, 2) },

  { key: "max_tokens", section: "model", label: "Max output tokens",
    description: "0 lets the model decide.",
    control: { kind: "number", min: 0, max: 128000, step: 256 },
    default: 0, validate: clampNum(0, 128000) },

  { key: "top_p", section: "model", label: "Top-p",
    control: { kind: "slider", min: 0, max: 1, step: 0.01 },
    default: 1, validate: clampNum(0, 1) },

  { key: "reasoning_effort", section: "model", label: "Reasoning effort",
    description: "How hard the model thinks before answering. Off leaves the provider default. Maps to each backend's native knob.",
    keywords: ["thinking", "reasoning", "effort", "budget", "o1", "o3"],
    control: { kind: "select", options: [
      { value: "off", label: "Off" }, { value: "minimal", label: "Minimal" },
      { value: "low", label: "Low" }, { value: "medium", label: "Medium" },
      { value: "high", label: "High" }]},
    default: "off" },

  { key: "base_url", section: "model", label: "Base URL override",
    description: "Point at a proxy, Azure, or a local server. Blank uses the provider default.",
    keywords: ["endpoint", "proxy", "azure", "ollama", "lm studio"],
    control: { kind: "text", placeholder: "https://api.openai.com/v1" },
    default: "", requiresRestart: true },

  { key: "api_key", section: "model", label: "API key",
    description: "Stored in the macOS keychain, never in the settings file. Blank uses the environment.",
    keywords: ["token", "secret", "credential", "openai"],
    control: { kind: "text", secret: true },
    // The engine refuses to export anything shorter than 20 characters, so
    // without this the field accepted a typo, stored it, echoed it back masked
    // as if it were set, and every turn failed as though no key existed.
    validate: (v) => (!v || String(v).length >= 20
      ? null
      : "That looks too short for an API key. Leave it blank to use the environment."),
    default: "", requiresRestart: true },

  // ---- Chat ---------------------------------------------------------------
  { key: "system_prompt", section: "chat", label: "System prompt",
    description: "Prepended to every conversation. Blank uses the default.",
    keywords: ["personality", "instructions", "persona"],
    control: { kind: "text", multiline: true, placeholder: "You are a careful assistant…" },
    default: "" },

  { key: "auto_title", section: "chat", label: "Name chats automatically",
    description: "Uses the first message as the title.",
    control: { kind: "toggle" }, default: true },

  { key: "show_reasoning", section: "chat", label: "Show reasoning",
    description: "Display the model's thinking when it emits any.",
    control: { kind: "toggle" }, default: true },

  { key: "collapse_reasoning", section: "chat", label: "Collapse reasoning by default",
    control: { kind: "toggle" }, default: false,
    visibleWhen: (g) => g("show_reasoning") === true },

  { key: "show_stats", section: "chat", label: "Show token stats",
    description: "Characters, duration and time to first token under each reply.",
    control: { kind: "toggle" }, default: true },

  { key: "condense_paste", section: "chat", label: "Condense long pastes",
    description: "Text longer than this becomes an attachment instead of filling the context.",
    keywords: ["clipboard", "context"],
    control: { kind: "select", options: [
      { value: 0, label: "Off" }, { value: 2000, label: "2,000 characters" },
      { value: 4000, label: "4,000 characters" }, { value: 8000, label: "8,000 characters" },
    ]}, default: 4000 },

  // ---- Appearance ---------------------------------------------------------
  { key: "theme", section: "appearance", label: "Theme",
    control: { kind: "segmented", options: [
      { value: "system", label: "System" }, { value: "light", label: "Light" },
      { value: "dark", label: "Dark" }]},
    default: "system" },

  { key: "font_size", section: "appearance", label: "Text size",
    description: "Scales the whole interface \u2014 messages, sidebar, settings and composer.",
    keywords: ["scale", "zoom", "bigger", "smaller", "interface"],
    control: { kind: "select", options: [
      { value: 13, label: "13 px" }, { value: 14, label: "14 px" },
      { value: 15, label: "15 px" }, { value: 16, label: "16 px" },
      { value: 18, label: "18 px" }, { value: 20, label: "20 px" }]},
    default: 15 },

  { key: "code_font_size", section: "appearance", label: "Code text size",
    control: { kind: "number", min: 10, max: 20, step: 1 },
    default: 12, validate: clampNum(10, 20) },

  { key: "reduce_motion", section: "appearance", label: "Reduce motion",
    control: { kind: "segmented", options: [
      { value: "system", label: "System" }, { value: "on", label: "On" },
      { value: "off", label: "Off" }]},
    default: "system" },

  // ---- Safety -------------------------------------------------------------
  { key: "approval_mode", section: "safety", label: "Tool approval",
    description: "How tool calls that touch your files are approved before running.",
    keywords: ["permissions", "confirm", "yolo", "sandbox"],
    control: { kind: "select", options: [
      { value: "ask",   label: "Ask every time" },
      { value: "smart", label: "Ask for risky actions" },
      { value: "never", label: "Never ask" }]},
    default: "ask",
    confirm: { when: (_p, n) => n === "never",
               message: "Tools will read your files without asking. Continue?" } },

  { key: "approval_timeout", section: "safety", label: "Approval timeout",
    description: "Seconds to wait before declining an unanswered request.",
    control: { kind: "number", min: 10, max: 3600, step: 10, unit: "s" },
    default: 300, validate: clampNum(10, 3600),
    visibleWhen: (g) => g("approval_mode") !== "never" },

  { key: "confirm_delete", section: "safety", label: "Confirm before deleting a chat",
    control: { kind: "toggle" }, default: true },

  // ---- General ------------------------------------------------------------
  { key: "launch_at_login", section: "general", label: "Open at login",
    control: { kind: "toggle" }, default: false, requiresRestart: true },

  { key: "check_updates", section: "general", label: "Check for updates automatically",
    control: { kind: "toggle" }, default: true },

  // ---- Data ---------------------------------------------------------------
  // Actions, not values. They carry no `default` and are skipped by save,
  // reset and search-by-value, but still get a row and an anchor for free.
  { key: "export_chats", section: "data", label: "Export all conversations",
    description: "Downloads every transcript as JSON.",
    keywords: ["backup", "download", "json"],
    control: { kind: "action", verb: "Export" }, action: "export" },

  { key: "open_data_dir", section: "data", label: "Data folder",
    description: "Transcripts and settings live outside the app bundle, so an update cannot take them with it.",
    keywords: ["storage", "location", "finder", "backup"],
    control: { kind: "action", verb: "Show path" }, action: "reveal" },

  { key: "clear_chats", section: "data", label: "Delete all conversations",
    description: "Cannot be undone.",
    keywords: ["reset", "wipe", "clear"],
    control: { kind: "action", verb: "Delete all", danger: true }, action: "clear",
    confirm: { when: () => true,
               message: "Delete every conversation? This cannot be undone." } },

  // ---- About --------------------------------------------------------------
  { key: "version", section: "about", label: "PraisonAI Desktop",
    control: { kind: "readout", value: () =>
      globalThis.__PRAISONAI_DESKTOP_VERSION__ || "unknown" } },

  { key: "agents_version", section: "about", label: "PraisonAI Agents",
    control: { kind: "readout", value: () =>
      globalThis.__PRAISONAI_AGENTS_VERSION__ || "unknown" } },

  { key: "engine_status", section: "about", label: "Engine",
    description: "The Python process this window is talking to.",
    control: { kind: "readout", value: (ctx) => ctx.engine || "not connected" } },

  { key: "logs_link", section: "about", label: "Engine log",
    control: { kind: "action", verb: "Open" }, action: "logs" },

  { key: "check_now", section: "about", label: "Check for updates",
    control: { kind: "action", verb: "Check" }, action: "update" },

  // ---- Integrations -------------------------------------------------------
  { key: "mcp_servers", section: "integrations", label: "MCP servers",
    description: "Saved for a future release. Servers listed here are stored only \u2014 the engine does not launch them yet, so the model cannot use them.",
    keywords: ["tools", "model context protocol", "stdio", "extensions"],
    control: { kind: "action", verb: "Manage" }, action: "mcp" },
];

// A duplicate key would silently shadow, so fail at load instead.
const seen = new Set();
for (const s of SETTINGS) {
  if (seen.has(s.key)) throw new Error(`duplicate setting key: ${s.key}`);
  seen.add(s.key);
}

const DEFAULTS = Object.fromEntries(SETTINGS.map((s) => [s.key, s.default]));

/** Search entries derive from the registry, never a parallel list, and respect
 *  visibleWhen -- so search can never return a row that cannot be shown. */
export function searchSettings(query, get) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const terms = q.split(/\s+/);
  const scored = [];
  for (const s of SETTINGS) {
    if (s.visibleWhen && !s.visibleWhen(get)) continue;
    const hay = [s.label, s.description || "", ...(s.keywords || []), s.key]
      .join(" ").toLowerCase();
    if (!terms.every((t) => hay.includes(t))) continue;
    const l = s.label.toLowerCase();
    scored.push({ s, score: l === q ? 100 : l.startsWith(q) ? 90
      : l.includes(q) ? 80 : (s.keywords || []).some((k) => k.includes(q)) ? 70 : 50 });
  }
  return scored.sort((a, b) => b.score - a.score).map((x) => x.s);
}
