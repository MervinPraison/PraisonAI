/**
 * The entry point. The only file that builds anything concrete.
 *
 * `tools/bundle.mjs` has defaulted its entry to this path since it was
 * written, and until now the file did not exist -- so `npm run build` failed
 * on a missing file and the webview gate had never once run against the real
 * import graph. Every layer below was a library; this is what makes them an
 * application.
 *
 * It stays deliberately thin. Anything with a decision in it lives in `ui/`
 * as a pure function, and anything that touches a port lives in `core/`. What
 * is left here is: choose a platform, boot, dispatch a route, paint, and
 * translate a tap into a call. That list is short on purpose, because this is
 * the one file no unit test can fully reach.
 */
import { createApp, type App } from "./boot.ts";
import { detectPlatform, type Platform } from "./platform.ts";
import { enginesFor, ENGINE_REMOTE_HTTP, SETTING_DEFS } from "./registry.ts";
import { intentFrom, type Actionable, type Intent } from "./intents.ts";
import { applyOps, emptyNodes, type RowNodes } from "./dom.ts";
import { installCrashHandler } from "./crash.ts";
import { emptyRender, reconcile, type RenderState } from "../../ui/src/render/reconcile.ts";
import { buildTranscript, type Row } from "../../ui/src/transcript/view-model.ts";
import type { RunView } from "../../core/src/run/controller.ts";
import type { Route } from "../../ui/src/router.ts";
import { en, type Strings } from "../../ui/src/i18n/strings.ts";
import { announce, initialAnnouncer, type AnnouncerState } from "../../ui/src/a11y/announce.ts";
import { createScreens } from "./mount.ts";
import { transition, screenFor, type ScreenId } from "../../ui/src/screens.ts";
import { routeTitle, chatRowName } from "../../ui/src/a11y/names.ts";
import {
  focusForRoute,
  headingId,
  screenAnnouncement,
  type FocusTarget,
  type Navigation,
} from "../../ui/src/a11y/focus.ts";
import { buildSettings, validateInput, type ValueRow } from "../../ui/src/settings/view-model.ts";
import { buildChatList } from "../../ui/src/chats/list-view-model.ts";
import type { ChatSummary, StoredMessage } from "../../core/src/chat/repository.ts";
import { createBundle } from "../../ui/src/i18n/bundle.ts";
import { resolveLocale, logicalInsets } from "../../ui/src/i18n/locale.ts";
import { geometryOf, initialLayout, withInsets, withKeyboard } from "../../ui/src/layout/insets.ts";
import {
  emptyComposer,
  setDraft,
  submit as submitComposer,
  keyAction,
  heightFor,
  lineCountOf,
  draftOf,
  type ComposerState,
} from "../../ui/src/composer/composer.ts";
import {
  initialFollow,
  onContentChanged,
  onScroll,
  jumpToLatest,
  shouldShowJumpToLatest,
  type FollowState,
  type ScrollMetrics,
} from "../../ui/src/transcript/scroll.ts";
import type { EngineChoice } from "./engines.ts";
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";
import { createPraisonTsEngine, type RunPersistence } from "../../engines/src/praisonai-ts/engine.ts";
import type { PraisonAgent } from "../../engines/src/praisonai-ts/agent-api.ts";
import type { SettingDef, SettingsFacade } from "../../core/src/settings/store.ts";
import type { IgnoredReason } from "../../protocol/src/decode.ts";
import type { HttpPort } from "../../core/src/ports/http.ts";

/** The one member of praisonai's `Agent` constructor this seam uses. Declared
 *  structurally, never imported -- `agent-api.ts` exists precisely so no
 *  `praisonai` type crosses into this package; `check:upstream` is the
 *  out-of-band check that the real `Agent` still matches. */
interface PraisonAgentModule {
  new (config: { instructions: string; llm?: string }): PraisonAgent;
}

/**
 * The in-process praisonai-ts engine, built lazily.
 *
 * DYNAMIC import, and through a runtime-computed specifier so NEITHER tsc nor
 * esbuild pulls `praisonai` into this package. That preserves the invariant
 * `agent-api.ts` documents: `praisonai` is not a dependency here and cannot be
 * until its Agent graph is bundleable for a webview -- its bare `crypto` and
 * `events` imports are import-time fatal (#4437), and its own sources do not
 * even typecheck under this config (which is why `check:upstream` runs the
 * coupling check out of band). Behind a lazy import the app still builds and
 * ships with the remote engine, and the in-process one is OFFERED -- its agent
 * module loading only where praisonai-ts is resolvable at run time.
 *
 * The engine takes a `createAgent` factory, not an agent: the model comes from
 * settings, which can change between turns.
 */
async function createInProcessEngine(
  persistence: RunPersistence,
  settings: SettingsFacade,
): Promise<AgentEnginePort> {
  const settingString = (key: string, fallback: string): string => {
    const value = settings.get(key);
    return typeof value === "string" && value !== "" ? value : fallback;
  };
  return createPraisonTsEngine({
    persistence,
    createAgent: async (): Promise<PraisonAgent> => {
      // Computed, not a literal: a literal specifier would make tsc pull the
      // untypecheckable upstream sources and esbuild bundle their import-time-
      // fatal builtins. This keeps both graphs clean and the engine offerable.
      const specifier = ["..", "..", "..", "praisonai-ts", "src", "agent", "simple.ts"].join("/");
      // The import can REJECT: this specifier resolves at run time, and where
      // praisonai-ts is not on disk (the shipping webview bundles only dist/,
      // #4437) the module is simply absent. Left unwrapped, that rejection is
      // an opaque "cannot find module" from deep inside the engine's run loop.
      // Re-thrown as a plain Error, engine.ts turns it into a recoverable
      // `error` event through its existing catch -- the named, on-screen
      // failure engines.ts argues for, not a crash. This does NOT let the
      // engine into the shipping picker (registry.ts keeps it out of
      // engineId.choices); it makes the one path that offers it honest.
      let mod: { Agent: PraisonAgentModule };
      try {
        mod = (await import(specifier)) as { Agent: PraisonAgentModule };
      } catch (cause) {
        throw new Error(
          "the in-process engine is unavailable in this build: praisonai-ts could not be loaded",
          { cause },
        );
      }
      return new mod.Agent({
        instructions: "You are a helpful assistant.",
        llm: settingString("model", "gpt-4o-mini"),
      });
    },
    newMsgId: () => globalThis.crypto.randomUUID(),
  });
}

/**
 * The engines the shipping composition root offers, in picker order.
 *
 * Extracted and exported so a test asserts the in-process engine is on offer
 * rather than that a factory literal appears in `mount` -- the house rule this
 * package keeps by. Running the agent loop in-process is the reason
 * praisonai-mobile exists, and until `main.ts` supplied `createInProcess` the
 * whole of `engines/src/praisonai-ts/` was unreachable from the application.
 */
export function appEngines(deps: {
  readonly settings: SettingsFacade;
  readonly http: HttpPort;
  readonly persistence: RunPersistence;
  readonly onIgnored: (reason: IgnoredReason, detail: string) => void;
}): readonly EngineChoice[] {
  return enginesFor({
    settings: deps.settings,
    http: deps.http,
    persistence: deps.persistence,
    onIgnored: deps.onIgnored,
    createInProcess: (persistence) => createInProcessEngine(persistence, deps.settings),
  });
}

/**
 * The engine to start with when settings name none.
 *
 * `remote-http` on every platform, for now, and the reason is a hard fact about
 * this build rather than a preference: the webview ships only `dist/app.js`
 * (build-webview.mjs bundles `app/src/main.ts` and copies nothing else), and
 * the in-process engine reaches praisonai-ts through a RUNTIME-computed import
 * that is deliberately outside that bundle (#4437). So on a real device the
 * in-process engine's module is simply ABSENT -- its first turn rejects with
 * "the in-process engine is unavailable in this build". Making it the device
 * DEFAULT would therefore swap the old "not answering" warning (which at least
 * names Settings as the fix) for a first prompt that fails with no recovery,
 * and would do it on the exact path registry.ts keeps the engine OUT of the
 * shipping picker to avoid ("a picker must not offer a choice that bricks the
 * app"). Until #4437 makes praisonai-ts resolvable inside the webview, the
 * honest first-launch default stays the remote engine.
 *
 * A second reason the ternary this replaced was wrong: `Platform["kind"]` is
 * only `"tauri" | "web"`, and DESKTOP Tauri (`cargo tauri dev`) reports
 * `"tauri"` too -- so keying the in-process engine off `kind === "tauri"` also
 * flipped the desktop/dev flow away from the remote engine it exists for, with
 * no way here to tell a phone from a laptop.
 *
 * Kept as an exported function, taking the platform kind, so the seam is ready
 * for the day a device can be told apart AND the engine ships -- and so a test
 * drives it directly rather than asserting an expression appears in `mount`.
 * The persisted `engineId` still wins over this (see `chosenStringOr` in
 * boot.ts), so it only ever decides the very first launch.
 */
export function defaultEngineIdFor(_kind: Platform["kind"]): string {
  return ENGINE_REMOTE_HTTP;
}

export interface MountDeps {
  readonly root: HTMLElement;
  readonly platform?: Platform;
  readonly strings?: Strings;
  readonly now?: () => number;
  readonly newChatId?: () => string;
  /** The locales the user prefers, most-preferred first. Injected so a test is
   *  deterministic; defaults to the host's `navigator.languages`. */
  readonly locales?: readonly string[];
}

/**
 * The locale to lay the app out in.
 *
 * `main.ts` used to pass `locale: "en"` as a literal, so every RTL user got an
 * LTR layout and the direction logic in ui/src/i18n/locale.ts was unreachable.
 * The English table is the only translation that ships today, so `resolveLocale`
 * matches the user's request against `["en"]` and falls back to English -- but
 * `createBundle` still derives `direction` from the *requested* tag, so an
 * Arabic device lays out right-to-left even while it reads English words. That
 * is the honest state until more tables exist, and it is what makes the #4607
 * fix reachable.
 */
export function requestedLocales(deps: MountDeps): readonly string[] {
  if (deps.locales !== undefined) return deps.locales;
  const nav = (globalThis as { navigator?: { languages?: readonly string[]; language?: string } })
    .navigator;
  if (nav === undefined) return ["en"];
  if (Array.isArray(nav.languages) && nav.languages.length > 0) return nav.languages;
  return [nav.language ?? "en"];
}

/** A screen's focusable heading, carrying `tabindex="-1"` so focus.ts can move
 *  focus to it on a route change (a heading is not focusable otherwise). */
function screenHeading(doc: Document, route: Route, strings: Strings): HTMLElement {
  const heading = doc.createElement("h2");
  heading.className = "screen-heading";
  heading.setAttribute("tabindex", "-1");
  heading.dataset["focusId"] = headingId(route);
  heading.textContent = routeTitle(strings, route);
  return heading;
}

/**
 * The editable control for one value row, wired to `facade.set`.
 *
 * A `choice` renders a `<select>`, everything else a `<textarea>`-free
 * `<input>`. The change is validated through the SAME pure `validateInput`
 * the view model exports -- parse, then the def's own `validate` -- so a value
 * the store would refuse is refused HERE, at the field, rather than accepted
 * into the UI and silently dropped by `set`. On accept it persists; on refuse
 * the field is reset to the last stored value so the screen never shows a value
 * that is not actually stored.
 *
 * This is the recovery path the remote-http default depends on: a phone reaches
 * no `127.0.0.1:8765`, and until now `baseUrl` could be READ on the settings
 * screen but not CHANGED -- `facade.set` and `validateInput` had no caller, so
 * a first launch that could not reach the engine had no way to point it at one.
 */
function settingControl(doc: Document, def: SettingDef, row: ValueRow, settings: SettingsFacade): HTMLElement {
  const stored = (): string => String(settings.get(def.key) ?? def.default);
  const reset = (): void => {
    if (control.tagName === "SELECT" || control.tagName === "INPUT") control.value = stored();
  };

  // A refused write must not leave the field showing a value the store rejected.
  // `settings.set` can also REJECT, not merely return false: it persists through
  // StoragePort, which raises on a real device (SecurityError with site data
  // blocked, QuotaExceededError under storage pressure). Left to float, that
  // rejection reaches the global crash handler and replaces the WHOLE app with
  // the fatal screen -- the exact escalation the chat-list load guards against
  // below. A failed write must stay LOCAL: reset the field to what is actually
  // stored, so the screen never shows a value the next launch will not read.
  const commit = async (raw: string): Promise<void> => {
    const validated = validateInput(def, raw);
    if (validated === null) return reset();
    try {
      if (!(await settings.set(def.key, validated))) reset();
    } catch {
      reset();
    }
  };

  let control: HTMLElement & { value: string };
  if (row.control === "choice" && row.choices !== null) {
    const select = doc.createElement("select") as HTMLElement & { value: string };
    for (const choice of row.choices) {
      const option = doc.createElement("option") as HTMLElement & { value: string };
      option.value = String(choice);
      option.textContent = String(choice);
      select.append(option);
    }
    select.value = stored();
    select.addEventListener("change", () => void commit(select.value));
    control = select;
  } else {
    const input = doc.createElement("input") as HTMLElement & { value: string; type: string };
    input.type = row.control === "number" ? "number" : "text";
    input.value = stored();
    // `change`, not `input`: persist when the field is committed (blur/Enter),
    // not on every keystroke, so a half-typed address is never stored and
    // `set` is not called on each character.
    input.addEventListener("change", () => void commit(input.value));
    control = input;
  }
  control.className = "setting-value setting-input";
  control.setAttribute("aria-label", row.label);
  return control;
}

/**
 * The settings screen, built from the live registry via `buildSettings`.
 *
 * Data-driven, so a setting added to the registry appears here without a code
 * change -- the whole reason settings/view-model.ts renders from `facade.defs()`
 * rather than a hard-coded list. `value` rows are EDITABLE: a phone has no
 * engine to reach at `127.0.0.1:8765`, and the only recovery for the remote
 * default is to change `baseUrl` here -- which was impossible while every row
 * rendered as a read-only `<span>`. Secret rows stay presence-only (the facade
 * has no getter for a secret, by design).
 */
export function buildSettingsScreen(
  doc: Document,
  settings: SettingsFacade,
  strings: Strings,
): HTMLElement {
  const section = doc.createElement("section");
  section.className = "screen screen-settings";
  section.append(screenHeading(doc, { name: "settings" }, strings));

  const defByKey = new Map(settings.defs().map((def) => [def.key, def]));

  const view = buildSettings(settings);
  for (const warning of view.warnings) {
    const note = doc.createElement("p");
    note.className = "row row-notice";
    note.dataset["tone"] = "warning";
    note.textContent = warning.text;
    section.append(note);
  }
  for (const group of view.sections) {
    const title = doc.createElement("h3");
    title.className = "settings-section";
    title.textContent = group.title;
    section.append(title);
    for (const row of group.rows) {
      const el = doc.createElement("div");
      el.className = `row row-setting row-setting-${row.kind}`;
      el.dataset["settingKey"] = row.key;
      const label = doc.createElement("span");
      label.className = "setting-label";
      label.textContent = row.label;
      el.append(label);
      const def = row.kind === "value" ? defByKey.get(row.key) : undefined;
      if (row.kind === "value" && def !== undefined) {
        el.append(settingControl(doc, def, row, settings));
      } else {
        const value = doc.createElement("span");
        value.className = "setting-value";
        value.textContent = row.kind === "secret" ? row.presence : String(row.value);
        el.append(value);
      }
      section.append(el);
    }
  }
  return section;
}

/**
 * The chat list, built from `session.list()` and `listUnreadable()`.
 *
 * Both lists, deliberately: a chat that failed to parse is a row here rather
 * than a conversation that silently vanished -- the promise list-view-model.ts
 * and repository.ts make together, and which only a renderer of the second list
 * can keep.
 */
export function buildChatsScreen(
  doc: Document,
  summaries: readonly ChatSummary[],
  unreadableIds: readonly string[],
  nowMs: number,
  strings: Strings,
): HTMLElement {
  const section = doc.createElement("section");
  section.className = "screen screen-chats";
  section.append(screenHeading(doc, { name: "chats" }, strings));

  const view = buildChatList(summaries, unreadableIds, nowMs);
  if (view.state === "none") {
    const empty = doc.createElement("p");
    empty.className = "empty";
    empty.textContent = strings.chatsEmpty;
    section.append(empty);
    return section;
  }
  if (view.state === "all-unreadable") {
    const note = doc.createElement("p");
    note.className = "row row-notice";
    note.dataset["tone"] = "warning";
    note.textContent = strings.chatsAllUnreadable(view.unreadableCount);
    section.append(note);
  }
  for (const row of view.rows) {
    const el = doc.createElement("button");
    el.type = "button";
    el.className = `row row-chat row-chat-${row.kind}`;
    // A tap on an unreadable row has nowhere useful to go, so only real chats
    // carry the open-chat intent -- intents.ts refuses a missing chatId anyway.
    if (row.kind === "chat") {
      el.dataset["action"] = "open-chat";
      el.dataset["chatId"] = row.id;
    }
    el.setAttribute("aria-label", chatRowName(strings, row));
    el.textContent = row.title;
    section.append(el);
  }
  return section;
}

/** A crash-screen renderer. Text only, and no dependency on anything that may
 *  itself be the thing that broke. */
function renderFatal(root: HTMLElement, message: string): void {
  root.textContent = "";
  const box = root.ownerDocument.createElement("div");
  box.className = "empty";
  box.setAttribute("role", "alert");
  box.textContent = message;
  root.append(box);
}

/**
 * What to announce after a Stop, or null when there is nothing to say.
 *
 * Extracted so a test calls it: `mount` needs a whole fake SSE transport to
 * drive, and the part that can actually be wrong is this decision. The house
 * rule -- extract the expression rather than assert it appears in the source.
 *
 * The controller returns the engine's own answer, and both the scripted engine
 * and the conformance contract go out of their way to keep that boolean
 * honest. Discarding it here made a refused Stop look exactly like an accepted
 * one, because the button label flips off `turn.phase`, which settles either
 * way -- while the run kept generating and kept billing.
 */
export function stopNotice(stopped: boolean, strings: Strings): string | null {
  return stopped ? null : strings.stopRefused;
}

/**
 * A reopened conversation's stored messages, as reconciler rows.
 *
 * Built as real `Row`s -- not raw `<p>` nodes -- so the transcript that history
 * paints into is the SAME render state the next turn's stream appends to. The
 * defect this replaces reset `render` to empty and appended untracked nodes, so
 * the next turn reconciled from nothing and inserted its rows above the history.
 *
 * Ids carry a `history:` prefix and the message index, so they are stable
 * (a re-open paints the same rows, not duplicates) and cannot collide with a
 * live turn's `text:N` ids -- a collision would make the first streamed
 * paragraph update a history row in place instead of appending after it.
 */
export function historyRows(messages: readonly StoredMessage[]): readonly Row[] {
  return messages.map((message, index) => ({
    kind: "text",
    id: `history:${index}:${message.role}`,
    text: message.content,
    streaming: false,
  }));
}

/** `createApp`, with a thrown failure turned into the same typed result the
 *  anticipated failures already produce. */
async function bootOrFail(
  options: Parameters<typeof createApp>[0],
): Promise<Awaited<ReturnType<typeof createApp>>> {
  try {
    return await createApp(options);
  } catch (error) {
    return {
      ok: false,
      reason: "storage_unavailable",
      detail: error instanceof Error ? error.message : String(error),
    } as Awaited<ReturnType<typeof createApp>>;
  }
}

export async function mount(deps: MountDeps): Promise<App | null> {
  const strings = deps.strings ?? en;
  const root = deps.root;
  const doc = root.ownerDocument;
  // Installed BEFORE anything else can throw -- and `detectPlatform()` is
  // something that can throw: it reads `window.localStorage`, which raises
  // SecurityError in a WKWebView with site data blocked. It used to run first,
  // directly contradicting this comment, and a throw there left the root
  // completely empty: a blank white page, no crash screen, on a device nobody
  // can attach a debugger to.
  const owner = doc.defaultView;
  installCrashHandler({
    ...(owner === null ? {} : { view: owner }),
    onCrash: () => renderFatal(root, strings.crashed),
  });

  const platform = deps.platform ?? detectPlatform();

  // ---- locale and direction ----------------------------------------------
  // Detected, not the literal "en" this used to hardcode. The English table is
  // the only one that ships, so `resolveLocale` falls back to it -- but the
  // bundle's direction comes from the REQUESTED tag, so an Arabic device lays
  // out right-to-left, which is what makes the #4607 direction fix reachable.
  const requested = requestedLocales(deps);
  // The tag the string table is for: matched against what actually ships, so an
  // "en-GB" request lands on "en" instead of a blank screen.
  const activeLocale = resolveLocale(requested, ["en"], "en");
  // Direction from the tag the USER asked for, not the resolved one: an Arabic
  // device reading English words still lays out right-to-left.
  const bundle = createBundle(requested[0] ?? "en", {}, "silent");
  root.setAttribute("dir", bundle.direction);

  // ---- the frame the app paints into -------------------------------------
  const screen = doc.createElement("div");
  screen.className = "screen";
  screen.dataset["screen"] = "chat";

  const bar = doc.createElement("header");
  bar.className = "topbar";
  const title = doc.createElement("h1");
  title.className = "screen-heading";
  title.setAttribute("tabindex", "-1");
  title.dataset["focusId"] = headingId({ name: "chat", chatId: "" });
  const toChats = doc.createElement("button");
  toChats.type = "button";
  toChats.dataset["action"] = "navigate";
  toChats.dataset["route"] = "chats";
  toChats.textContent = strings.routeChats;
  title.textContent = strings.appName;
  const newChat = doc.createElement("button");
  newChat.type = "button";
  newChat.dataset["action"] = "new-chat";
  newChat.textContent = strings.newChat;
  const toSettings = doc.createElement("button");
  toSettings.type = "button";
  toSettings.dataset["action"] = "navigate";
  toSettings.dataset["route"] = "settings";
  toSettings.textContent = strings.routeSettings;
  bar.append(title, toChats, newChat, toSettings);

  const transcript = doc.createElement("main");
  transcript.className = "transcript";
  // NOT a live region, deliberately. `reconcile`/`applyOps` mutate this
  // element on every publish, so `aria-live` here makes the reader restart on
  // each token batch and no sentence is ever finished -- and clearing it for a
  // new chat would announce the wipe. Announcements go through the policy in
  // ui/src/a11y/announce.ts and land in the small region below, which changes
  // only when there is something worth saying.
  transcript.setAttribute("role", "log");
  transcript.setAttribute("aria-label", strings.appName);

  const polite = doc.createElement("div");
  polite.className = "sr-only";
  polite.setAttribute("aria-live", "polite");
  const assertive = doc.createElement("div");
  assertive.className = "sr-only";
  // Assertive interrupts: an approval prompt blocks the run, so waiting
  // politely for the queue to drain is waiting for something that will not
  // happen until the user answers.
  assertive.setAttribute("aria-live", "assertive");

  const composer = doc.createElement("form");
  composer.className = "composer";
  const input = doc.createElement("textarea");
  input.rows = 1;
  // The message FIELD, not the button beside it. Labelling it with the
  // button's name announced the composer as "Send, edit text".
  input.setAttribute("aria-label", strings.composerLabel);
  const sendButton = doc.createElement("button");
  sendButton.type = "submit";
  sendButton.dataset["action"] = "send";
  sendButton.dataset["variant"] = "primary";
  sendButton.textContent = strings.actionSend;
  composer.append(input, sendButton);

  // Shown only when the user has scrolled up off the bottom of a streaming
  // transcript -- `scroll.ts` owns that decision, this is its affordance.
  const jumpLatest = doc.createElement("button");
  jumpLatest.type = "button";
  jumpLatest.className = "jump-latest";
  jumpLatest.dataset["action"] = "jump-latest";
  jumpLatest.textContent = strings.streaming;
  jumpLatest.hidden = true;

  screen.append(bar, transcript, jumpLatest, composer, polite, assertive);
  root.textContent = "";
  root.append(screen);

  // ---- boot ---------------------------------------------------------------
  let render: RenderState = emptyRender;
  const nodes: RowNodes = emptyNodes();
  let announcer: AnnouncerState = initialAnnouncer;

  // A reopened conversation's stored messages, as reconciler rows. The
  // controller only ever publishes the CURRENT turn -- it resets to
  // `initialTurn` on each run -- so history is not in the RunView. It is held
  // here and PREPENDED to every reconcile, so a follow-up turn's rows land
  // below it and a reconcile never emits `remove` for history it did not know
  // about. Empty for a fresh chat; cleared on New chat.
  let history: readonly Row[] = [];

  // ---- composer state (draft, key policy, autosize) ----------------------
  // The composer is data now, not just a <textarea>: a draft that survives a
  // trip to settings, an Enter-vs-Shift-Enter policy, and a clamped height. The
  // field mirrors this state; this state is the source of truth.
  let composerState: ComposerState = emptyComposer();
  const syncComposer = (): void => {
    const text = draftOf(composerState);
    if (input.value !== text) input.value = text;
    input.style.setProperty("height", `${heightFor(lineCountOf(text))}px`);
    sendButton.disabled = text.trim() === "";
  };

  // ---- follow-the-stream (scroll.ts) -------------------------------------
  let follow: FollowState = initialFollow;
  const metricsOf = (): ScrollMetrics => ({
    scrollTop: transcript.scrollTop,
    scrollHeight: transcript.scrollHeight,
    clientHeight: transcript.clientHeight,
  });
  const applyFollow = (): void => {
    jumpLatest.hidden = !shouldShowJumpToLatest(follow);
  };

  const publish = (view: RunView): void => {
    const built = buildTranscript(view.turn, view.approvals);
    // History first, then the live turn. `history` is empty for a fresh chat,
    // so this is a no-op there; for a reopened chat it keeps the restored
    // conversation ABOVE the turn now streaming and inside the render state, so
    // the diff updates the live rows without removing the history.
    const rows = history.length === 0 ? built.rows : [...history, ...built.rows];
    const diff = reconcile(render, rows);
    applyOps(transcript, nodes, diff.ops, strings);
    render = diff.next;

    // Coalesced to finished sentences and rate-limited: announcing every token
    // is unusable, announcing nothing makes the app opaque.
    const spoken = announce(announcer, {
      turn: view.turn,
      strings,
      locale: activeLocale,
      nowMs: Date.now(),
    });
    announcer = spoken.state;
    // Each region is assigned ONCE, with every utterance of that politeness
    // joined. Assigning per item overwrote the earlier ones in the same task,
    // so only the LAST survived to be read.
    //
    // Measured: a short answer completing inside one interval produced
    // [polite "The capital of France is Paris.", polite "Response complete"],
    // and a screen-reader user heard only "Response complete." That is exactly
    // the failure announce.ts rule 4 exists to prevent -- "the user would never
    // hear the end of the response" -- reintroduced at the single point where
    // the pure function meets the DOM.
    const polites = spoken.announcements.filter((a) => a.politeness !== "assertive");
    const assertives = spoken.announcements.filter((a) => a.politeness === "assertive");
    if (polites.length > 0) polite.textContent = polites.map((a) => a.text).join(" ");
    if (assertives.length > 0) assertive.textContent = assertives.map((a) => a.text).join(" ");

    const streaming = view.turn.phase === "streaming";
    sendButton.textContent = streaming ? strings.actionStop : strings.actionSend;
    sendButton.dataset["action"] = streaming ? "stop" : "send";
    // Stop is always tappable; Send is disabled on an empty draft. Guarding the
    // disable on the action keeps a streaming Stop from going dead because the
    // draft happens to be empty.
    sendButton.disabled = streaming ? false : draftOf(composerState).trim() === "";

    // New content asks to be scrolled to; whether it IS depends on scroll.ts.
    const outcome = onContentChanged(follow, metricsOf());
    follow = outcome.state;
    if (outcome.action.kind === "scrollTo") transcript.scrollTop = outcome.action.top;
    applyFollow();
  };

  // `createApp` returns a typed BootResult for the failures it anticipated --
  // an unknown engine, a protocol mismatch. It can also THROW, and did: an
  // unguarded `settingsStore.load()` propagates a StoragePort failure, which
  // is reachable on the real platform (SecurityError with site data blocked,
  // QuotaExceededError under the storage pressure platform.ts documents).
  //
  // The chrome is already built and appended by this point, so a rejection
  // here skipped the fatal screen AND the listener registrations below,
  // leaving a perfectly rendered app -- top bar, composer, green Send button
  // -- in which nothing whatsoever happened, forever.
  const mintChatId = deps.newChatId ?? ((): string => globalThis.crypto.randomUUID());

  const booted = await bootOrFail({
    storage: platform.storage,
    secrets: platform.secrets,
    time: platform.time,
    shell: platform.shell,
    // The factory receives the session boot just built, so the engine that
    // records a turn and the repository the UI reads are the same store.
    // The REAL settings facade, handed back by createApp once it has loaded
    // them. This used to be a stub whose `get` returned undefined, captured by
    // the engine at boot and never replaced -- so the engine address the user
    // set was read, stored, and thrown away in favour of the hardcoded default.
    engines: (persistence, settings, onIgnored) =>
      appEngines({ settings, http: platform.http, persistence, onIgnored }),
    settingDefs: SETTING_DEFS,
    // The default when settings name none, chosen by platform: the in-process
    // engine on a device (a phone has no `127.0.0.1:8765` to reach, and a
    // cleartext localhost address is refused by iOS ATS and Android), the
    // remote engine on desktop/dev where one actually runs. createApp prefers
    // the persisted `engineId` over this, so it only decides the first launch.
    engineId: defaultEngineIdFor(platform.kind),
    onPublish: publish,
    now: deps.now ?? (() => Date.now()),
    newChatId: mintChatId,
  });

  if (!booted.ok) {
    // A named failure, on screen. `app/src/engines.ts` promises exactly this
    // and nothing rendered it: an unusable engine used to be an unhandled
    // branch that left a blank page.
    //
    // Reached now only by a PERMANENT failure -- storage that will not open, a
    // protocol mismatch. An engine that is merely unreachable boots and warns
    // instead; see below.
    renderFatal(root, strings.bootFailed(booted.detail));
    return null;
  }

  const app = booted.app;

  // The engine is not answering, but the app is usable. Said out loud rather
  // than left for the first message to discover -- and assertive, because the
  // user is about to type into something that cannot reply yet.
  //
  // This branch exists because refusing to boot on an unreachable engine left
  // the user on an error screen with no way back: they cannot open Settings to
  // change the address, because Settings is where the address is changed.
  if (booted.notReady !== undefined) {
    const warning = doc.createElement("p");
    warning.className = "row row-notice";
    warning.dataset["tone"] = "warning";
    warning.textContent = strings.engineNotReady(booted.notReady.detail);
    transcript.append(warning);
    assertive.textContent = strings.engineNotReady(booted.notReady.detail);
  }

  // ---- the shell drives layout -------------------------------------------
  // Derived through `geometryOf`, not inline px. The pure derivation is what
  // makes the keyboard cover the home indicator (`max`, never `+`) and what
  // turns a WebView's mid-rotation NaN into 0 rather than a dropped style
  // declaration that drops the composer under the keyboard. The physical
  // left/right edges then become logical padding, so RTL puts the safe-area on
  // the leading edge.
  const applyGeometry = (): void => {
    let layout = initialLayout(platform.shell.insets);
    layout = withInsets(layout, platform.shell.insets);
    layout = withKeyboard(layout, platform.shell.keyboardHeightPx);
    const geometry = geometryOf(layout);
    screen.style.setProperty("--keyboard-height", `${geometry.composerBottomPx}px`);
    screen.style.setProperty("--inset-top", `${geometry.scrollTopPx}px`);
    const logical = logicalInsets(bundle.direction, geometry.composerLeftPx, geometry.composerRightPx);
    // The GUTTER is added here, not left to the stylesheet. An inline style
    // beats `app.css`'s `calc(var(--safe-area-inset-left) + .75rem)`, so
    // writing the bare inset put the composer flush against the screen edge
    // while the topbar and transcript kept their gutter -- measured at a 320px
    // viewport with no side insets: the textarea's left edge sat at x = 0.
    composer.style.setProperty("padding-inline-start", `calc(${logical.startPx}px + .75rem)`);
    composer.style.setProperty("padding-inline-end", `calc(${logical.endPx}px + .75rem)`);
  };
  applyGeometry();
  platform.shell.onInsetsChanged(applyGeometry);
  platform.shell.onKeyboardHeightChanged(applyGeometry);

  // ---- screens the router drives -----------------------------------------
  // The chat screen is retained (it holds scroll position and a live stream);
  // settings and chats are built on demand and rebuilt each visit. `transition`
  // decides what to mount, hide and destroy; this half only obeys it.
  const screens = createScreens({
    root,
    build: (id: ScreenId): HTMLElement => {
      if (id === "settings") return buildSettingsScreen(doc, app.settings, strings);
      if (id === "chats") {
        // A fresh snapshot each visit: a chat created since the list was last
        // seen must appear, and one deleted must be gone.
        const section = buildChatsScreen(doc, [], [], deps.now?.() ?? Date.now(), strings);
        void (async (): Promise<void> => {
          const [summaries, unreadable] = await Promise.all([
            app.session.list(),
            app.session.repository.listUnreadable(),
          ]);
          const fresh = buildChatsScreen(
            doc,
            summaries as readonly ChatSummary[],
            unreadable,
            deps.now?.() ?? Date.now(),
            strings,
          );
          section.textContent = "";
          for (const child of [...fresh.children]) section.append(child as HTMLElement);
        })().catch(() => {
          // Storage can reject while the list loads -- SecurityError with site
          // data blocked, QuotaExceededError. A floating rejection here reaches
          // the global crash handler and replaces the WHOLE app with the fatal
          // screen; a failed chat list must stay a LOCAL failure, so the user
          // can go back and keep using the conversation they are in.
          section.textContent = "";
          const notice = doc.createElement("p");
          notice.className = "row row-notice";
          notice.dataset["tone"] = "warning";
          notice.setAttribute("role", "alert");
          notice.textContent = strings.crashed;
          section.append(notice);
        });
        return section;
      }
      // "about" and "chat" have no builder here: chat is the pre-built root
      // screen, and about is not yet a route the app pushes.
      return doc.createElement("section");
    },
  });
  // The chat screen already exists; register it so `transition` treats it as
  // live and retains it rather than trying to build a second one.
  screens.nodes.set("chat", screen);

  // The element by its `data-focus-id`, searched under root. There is no
  // `querySelector` in the seam a test drives, and there does not need to be:
  // the set of focusable ids is tiny (a heading per live screen), so a walk is
  // both correct and cheap.
  const byFocusId = (id: string): HTMLElement | null => {
    if (id === "") return null;
    const stack: HTMLElement[] = [root];
    while (stack.length > 0) {
      const node = stack.pop();
      if (node === undefined) break;
      if (node.dataset["focusId"] === id) return node;
      for (const child of node.children) {
        if (child instanceof HTMLElement) stack.push(child);
      }
    }
    return null;
  };

  // Whatever the renderer must return to when a Back gesture pops a screen. A
  // pop restores focus to the control that opened the screen -- the chat row,
  // the settings button -- so the user lands where they were, not at the top of
  // a list they have to scroll down again.
  let restoreFocus: HTMLElement | null = null;

  // The three lines focus.ts deliberately does NOT do -- move focus, save it,
  // restore it -- because they are the only part it cannot unit test. Doing
  // less than this leaves the decision computed and discarded, which is the
  // very "focus falls to <body>" bug the whole module exists to prevent.
  const applyFocus = (target: FocusTarget): void => {
    switch (target.kind) {
      case "none":
        return;
      case "element": {
        byFocusId(target.id)?.focus();
        return;
      }
      case "restore": {
        // The saved element may be gone -- popping back after deleting the chat
        // you were viewing means the row you came from no longer exists -- so
        // fall back to the destination's heading rather than focusing nothing.
        const saved = restoreFocus;
        if (saved !== null && saved.isConnected) saved.focus();
        else byFocusId(target.fallbackId)?.focus();
        restoreFocus = null;
        return;
      }
    }
  };

  let currentRoute: Route | null = null;
  const showRoute = (route: Route, nav: Navigation): void => {
    const change = transition(currentRoute, route, screens.live());
    if (!change.noop) screens.apply(change);
    const focus = focusForRoute(currentRoute, route, nav);
    // Announce the screen change, so a route change is never silent to a
    // screen reader even when focus lands somewhere with a short name.
    if (focus.kind === "element" && focus.id !== "") {
      assertive.textContent = screenAnnouncement(strings, route);
    }
    // Then actually move focus. Computing the target and never applying it left
    // focus on the screen the user just left, or on <body> once that screen was
    // hidden -- exactly the failure focus.ts's ids exist to fix.
    applyFocus(focus);
    currentRoute = route;
  };
  // The router's root is `chats`, but the app opens on the chat screen; align
  // the two so the first back gesture behaves and `screenFor` agrees.
  currentRoute = { name: "chat", chatId: "" };
  screen.hidden = false;
  // The previous stack depth, to tell a push from a pop: a shorter stack is a
  // Back, a longer one a forward navigation. The replace below seeds it at 1.
  let previousDepth = 1;
  app.router.subscribe((stack) => {
    const top = stack[stack.length - 1];
    if (top === undefined) return;
    const nav: Navigation =
      stack.length < previousDepth ? "pop" : stack.length > previousDepth ? "push" : "replace";
    // Save the control the user is leaving from BEFORE the DOM changes, so a
    // later pop can return to it. Only on a push -- a pop consumes the saved
    // target, and a replace is not a place to come back to.
    if (nav === "push") {
      const active = doc.activeElement;
      restoreFocus = active instanceof HTMLElement ? active : null;
    }
    previousDepth = stack.length;
    showRoute(top, nav);
  });
  // Replace the router's `chats` root with the chat the app actually opens on,
  // so pushing `chats` later is a real navigation and not swallowed as a push
  // of the route already on top.
  app.router.replace({ name: "chat", chatId: "" });

  // ---- taps ---------------------------------------------------------------
  const chainOf = (target: EventTarget | null): Actionable[] => {
    const chain: Actionable[] = [];
    let node = target instanceof Element ? target : null;
    while (node !== null) {
      if (node instanceof HTMLElement) {
        chain.push({
          dataset: { ...node.dataset },
          ...(node instanceof HTMLButtonElement ? { disabled: node.disabled } : {}),
        });
      }
      node = node.parentElement;
    }
    return chain;
  };

  const perform = async (intent: Intent): Promise<void> => {
    switch (intent.kind) {
      case "send":
        return submit();
      case "stop": {
        const notice = stopNotice(await app.controller.stop(), strings);
        if (notice !== null) assertive.textContent = notice;
        return;
      }
      case "approve":
        await app.controller.decide(intent.approvalId, intent.choice);
        return;
      case "new-chat": {
        // Stop the turn FIRST. Clearing the screen without stopping left the
        // previous run streaming: the next token reconciled against an empty
        // render and re-inserted the old conversation's rows into what the
        // user believed was a fresh chat, where it then finished.
        void app.controller.stop();
        // And give the new conversation its own id. `setChat` was never called
        // anywhere in the app, so every request from every chat carried
        // `chat_id: "unassigned"` -- controller.ts says in as many words that
        // "an engine cannot tell two conversations apart if every turn claims
        // the same id".
        app.controller.setChat(mintChatId());
        app.session.reset();
        // A fresh chat has no history to keep above the next turn.
        history = [];
        render = emptyRender;
        nodes.nodes.clear();
        announcer = initialAnnouncer;
        transcript.textContent = ""; // safe now: this is no longer a live region
        // The live regions too. Resetting `announcer` clears the state that
        // decides what to SAY next; it does not empty the regions themselves,
        // so the previous conversation's answer stayed in the accessibility
        // tree of what the user believes is an empty chat. Not announced
        // again -- but still there for anyone navigating the page.
        polite.textContent = "";
        assertive.textContent = "";
        return;
      }
      case "navigate":
        app.router.push({ name: intent.route } as Route);
        return;
      case "open-chat": {
        // Reopen a previous conversation. `session.list()` had no app caller and
        // `session.open()` no way to be reached; this is the path from the chat
        // list back into a stored transcript.
        const opened = await app.session.open(intent.chatId);
        if (!opened) return;
        app.controller.setChat(intent.chatId);
        render = emptyRender;
        nodes.nodes.clear();
        announcer = initialAnnouncer;
        transcript.textContent = "";
        polite.textContent = "";
        assertive.textContent = "";
        // Paint the stored messages THROUGH the reconciler, not as raw nodes.
        //
        // Appending untracked `<p>` elements and resetting `render` to empty was
        // a defect: the next turn reconciled from an empty render state and
        // `applyOps` inserted its rows at index 0 -- ABOVE the history -- while
        // the manually appended messages stayed outside `render`/`nodes` and
        // could never be updated. The newest turn rendered above the older
        // conversation. Holding the history as real `Row`s and prepending it in
        // `publish` keeps it in the same coordinate system the stream appends to
        // AND makes it survive the next turn's reconcile.
        const chat = app.session.current();
        history = chat === null ? [] : historyRows(chat.messages);
        const seeded = reconcile(render, history);
        applyOps(transcript, nodes, seeded.ops, strings);
        render = seeded.next;
        app.router.push({ name: "chat", chatId: intent.chatId });
        return;
      }
      default:
        return;
    }
  };

  const submit = async (): Promise<void> => {
    // The field is the live edit; the composer state is the durable draft. Take
    // from the field so a test that sets `input.value` directly still sends, and
    // clear both -- `submitComposer` is what makes a double tap on send a no-op.
    const text = input.value.trim();
    if (text === "") return; // an empty send is a no-op, not an empty turn
    const busy = sendButton.dataset["action"] === "stop";
    composerState = setDraft(composerState, input.value);
    const result = submitComposer(composerState, busy);
    composerState = result.next;
    input.value = "";
    syncComposer();
    if (result.sent === null) return; // refused while a turn is in flight
    await app.controller.send(result.sent);
  };

  // ---- composer field <-> state ------------------------------------------
  input.addEventListener("input", () => {
    composerState = setDraft(composerState, input.value);
    input.style.setProperty("height", `${heightFor(lineCountOf(input.value))}px`);
    if (sendButton.dataset["action"] !== "stop") {
      sendButton.disabled = input.value.trim() === "";
    }
  });
  input.addEventListener("keydown", (event) => {
    const e = event as KeyboardEvent;
    const action = keyAction({
      key: e.key,
      shiftKey: e.shiftKey,
      altKey: e.altKey,
      ctrlKey: e.ctrlKey,
      metaKey: e.metaKey,
      isComposing: e.isComposing,
    });
    if (action === "send") {
      e.preventDefault();
      void submit();
    }
    // "newline" and "ignore" both let the field handle the key normally.
  });
  syncComposer();

  // ---- scroll follow ------------------------------------------------------
  transcript.addEventListener("scroll", () => {
    follow = onScroll(follow, metricsOf());
    applyFollow();
  });

  composer.addEventListener("submit", (event) => {
    event.preventDefault();
    void submit();
  });

  // Delegated on ROOT, not the chat screen: the settings and chats screens are
  // siblings of it, so a tap on a chat row would otherwise never be heard.
  root.addEventListener("click", (event) => {
    const target = event.target;
    // Jump-to-latest is not an intent (it is a scroll decision, not an engine
    // call), so it is handled here before the intent walk.
    const chain = chainOf(target);
    if (chain.some((el) => el.dataset["action"] === "jump-latest")) {
      const outcome = jumpToLatest(follow, metricsOf());
      follow = outcome.state;
      if (outcome.action.kind === "scrollTo") transcript.scrollTop = outcome.action.top;
      applyFollow();
      (event as { preventDefault(): void }).preventDefault();
      return;
    }
    const intent = intentFrom(chain);
    if (intent === null) return;
    (event as { preventDefault(): void }).preventDefault();
    void perform(intent);
  });

  return app;
}

// Auto-mount when loaded as a page, never when imported by a test.
const el = globalThis.document?.getElementById("root");
if (el !== null && el !== undefined) {
  void mount({ root: el });
}
