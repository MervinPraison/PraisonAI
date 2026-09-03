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
import { enginesFor, apiKeyFor, defaultEngineIdFor, settingDefsFor } from "./registry.ts";
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
import {
  buildSettings,
  labelOf,
  presenceLabel,
  validateInput,
  type SecretPresence,
  type SecretRow,
  type ValueRow,
} from "../../ui/src/settings/view-model.ts";
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
import {
  createPraisonTsEngine,
  type ConversationHistory,
  type RunPersistence,
} from "../../engines/src/praisonai-ts/engine.ts";
import { loadPraisonAgent, type PraisonAgentModule } from "../../engines/src/praisonai-ts/load-agent.ts";
import type { PraisonAgent } from "../../engines/src/praisonai-ts/agent-api.ts";
import { secretRefOf, type SettingDef, type SettingsFacade } from "../../core/src/settings/store.ts";
import type { SecretsPort } from "../../core/src/ports/secrets.ts";
import type { IgnoredReason } from "../../protocol/src/decode.ts";
import type { HttpPort } from "../../core/src/ports/http.ts";

/**
 * The in-process praisonai-ts engine, built lazily.
 *
 * `praisonai` is a dependency now, and it reaches the webview as a CHUNK: the
 * literal `import("praisonai/mobile")` in engines/praisonai-ts/load-agent.ts
 * is what lets esbuild split it out, so the shell that loads at first paint
 * stays at 66kB and the engine's ~1.3MB is fetched only when this factory
 * first runs. It used to be a runtime-computed specifier that kept `praisonai`
 * out of both tsc's and esbuild's graphs entirely -- necessary while its Agent
 * graph imported `crypto` and `events` statically (#4437), and the reason the
 * engine's module was simply ABSENT from every shipped build. `praisonai/mobile`
 * is the upstream entry without those imports; `tools/bundle.mjs` is what
 * proves that on every build.
 *
 * The engine takes a `createAgent` factory, not an agent: the model comes from
 * settings, which can change between turns.
 */
async function createInProcessEngine(
  persistence: RunPersistence,
  history: ConversationHistory,
  settings: SettingsFacade,
  secrets: SecretsPort,
  loadAgent: () => Promise<PraisonAgentModule>,
): Promise<AgentEnginePort> {
  const settingString = (key: string, fallback: string): string => {
    const value = settings.get(key);
    return typeof value === "string" && value !== "" ? value : fallback;
  };
  return createPraisonTsEngine({
    persistence,
    // The read side of the same store `persistence` writes to. The engine
    // builds a fresh Agent per turn -- the model and the key come from
    // settings and can change between messages -- so upstream's own
    // accumulation dies with each agent and the conversation has to be
    // restored explicitly on every turn.
    history,
    createAgent: async (): Promise<PraisonAgent> => {
      // The chunk is fetched here, on the first turn, not at create(): a
      // fetch that fails then surfaces through engine.ts's run loop as a
      // recoverable `error` event rather than as a factory that throws.
      const Agent = await loadAgent();
      /**
       * The key, read on EVERY turn.
       *
       * The engine is built once, at boot, and held for the session -- so a
       * key read here at construction would mean the key someone pastes into
       * Settings does not work until they force-quit the app. That is the
       * exact defect `enginesFor` fixed for `baseUrl`, and it is worse for a
       * credential: the failure it produces ("the OPENAI_API_KEY environment
       * variable is missing or empty") is the same message they were trying to
       * clear, so the app appears to have ignored them.
       *
       * The secret goes into a local and into the agent config and NOWHERE
       * else: not into settings state, not into a render tree, not into the
       * announcer. `SecretsPort` is reachable here because this is the
       * composition root; `ui/` holds a facade with no getter.
       */
      const apiKey = await apiKeyFor(secrets, settings.defs());
      return new Agent({
        instructions: "You are a helpful assistant.",
        llm: settingString("model", "gpt-4o-mini"),
        // Omitted rather than passed as "" or null when unset: upstream treats
        // a falsy apiKey as "fall back to the environment", and on a phone
        // there is no environment -- so the honest shape for "no key" is an
        // absent field and the provider's own missing-credential error.
        ...(apiKey === null ? {} : { apiKey }),
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
  /**
   * The keychain, handed to the ENGINE and to nothing else.
   *
   * Required rather than optional on purpose. An optional port is a
   * composition that can forget it and still build -- and what it builds is an
   * engine with no credential, which fails on the first message with a
   * provider error that names an environment variable no phone has. A missing
   * argument here is a typecheck failure instead.
   */
  readonly secrets: SecretsPort;
  readonly persistence: RunPersistence;
  /** Where prior turns come from. Required for the same reason `secrets` is:
   *  an optional one builds an engine that answers every message as though it
   *  were the first. */
  readonly history: ConversationHistory;
  readonly onIgnored: (reason: IgnoredReason, detail: string) => void;
  /** How the in-process engine's `Agent` class is fetched. Defaults to the
   *  real chunk loader. A test injects a rejecting one to drive the failure
   *  path, because with `praisonai` installed the real one simply succeeds. */
  readonly loadAgent?: () => Promise<PraisonAgentModule>;
}): readonly EngineChoice[] {
  const loadAgent = deps.loadAgent ?? loadPraisonAgent;
  return enginesFor({
    settings: deps.settings,
    http: deps.http,
    persistence: deps.persistence,
    history: deps.history,
    onIgnored: deps.onIgnored,
    createInProcess: (persistence, history) =>
      createInProcessEngine(persistence, history, deps.settings, deps.secrets, loadAgent),
  });
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
  /** How the in-process engine's `Agent` class is fetched. Defaults to the
   *  real chunk loader; a test hands in a scripted class so a first message
   *  can be driven into the in-process engine with no network and no key. */
  readonly loadAgent?: () => Promise<PraisonAgentModule>;
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
 * The editable control for one value row. MARKUP ONLY -- no listener.
 *
 * A `choice` renders a `<select>`, everything else a `<textarea>`-free
 * `<input>`, and the kind comes from `row.control` (the def), never from the
 * value: view-model.ts rule 4 -- one bad write to a hand-edited settings file
 * would otherwise turn a picker into a text box and the setting could never be
 * changed back.
 *
 * The control carries `data-action="set-setting"` and its key, and does
 * nothing else. Committing it used to happen inside a `change` listener
 * attached right here, which made settings the ONE affordance in the app that
 * did not go through `intents.ts` -- so the decision (which key, what was
 * typed, and whether a refusal is worth saying anything about) could only be
 * reached by synthesising events against a DOM, and the refusal path ended in
 * a field that silently snapped back. Delegated on root like every tap, the
 * decision is `intentFrom`'s and the write is `perform`'s, next to the live
 * region that has to announce it.
 *
 * This is the recovery path the remote-http default depends on: a phone
 * reaches no `127.0.0.1:8765`, and `baseUrl` could be READ on the settings
 * screen but not CHANGED, so a first launch that could not reach the engine
 * had no way to point it at one.
 */
function settingControl(doc: Document, def: SettingDef, row: ValueRow, settings: SettingsFacade): HTMLElement {
  let control: HTMLElement & { value: string };
  if (row.control === "choice" && row.choices !== null) {
    const select = doc.createElement("select") as HTMLElement & { value: string };
    for (const choice of row.choices) {
      const option = doc.createElement("option") as HTMLElement & { value: string };
      option.value = String(choice);
      option.textContent = String(choice);
      select.append(option);
    }
    control = select;
  } else {
    const input = doc.createElement("input") as HTMLElement & { value: string; type: string };
    input.type = row.control === "number" ? "number" : "text";
    control = input;
  }
  // From the STORE, not from `row.value`: identical today, and it stays
  // identical only while nothing repaints a row from a stale view.
  control.value = String(settings.get(def.key) ?? def.default);
  control.className = "setting-value setting-input";
  control.setAttribute("aria-label", row.label);
  // `change`, not `input`: a field commits on blur or Enter, so a half-typed
  // address is never stored and `set` is not called once per keystroke.
  // Delegated on root -- `change` bubbles.
  control.dataset["action"] = "set-setting";
  control.dataset["settingKey"] = def.key;
  return control;
}

/**
 * Where a refusal for one setting is written, and nothing until there is one.
 *
 * `role="alert"` and empty: an alert region that is created at the moment of
 * the failure is announced unreliably, so it exists from first paint and only
 * its text changes. `hidden` while empty, because an empty bordered box beside
 * a field reads as a rendering fault.
 */
function settingError(doc: Document, key: string): HTMLElement {
  const note = doc.createElement("p");
  note.className = "setting-error";
  note.dataset["settingError"] = key;
  note.setAttribute("role", "alert");
  note.hidden = true;
  return note;
}

/**
 * A secret row's controls: a masked field to set it, and a button to remove it.
 *
 * THREE properties, and each has a broken version that looks completely normal
 * on screen.
 *
 *  1. `value` IS NEVER ASSIGNED. Not "assigned a masked stand-in" -- never
 *     assigned. `settingControl` above reads the store to seed its field, and
 *     the mirror of that line here would be the leak: `SettingsFacade` has no
 *     secret getter precisely so a view "cannot accidentally fault a key into
 *     the render tree where it can reach a log, a crash report or a
 *     screenshot" (store.ts). The field paints empty on every visit, and
 *     `syncSecret` empties it again after every commit, so the value is in the
 *     DOM only while the user is holding it there.
 *  2. `type="password"`, so a shoulder-surfer and a screen recording see dots.
 *     `autocomplete="off"` and `spellcheck="false"` with it: a browser or
 *     webview that offers to remember the field, or that ships an unrecognised
 *     token off to a spellchecker, has moved the credential somewhere nobody
 *     chose.
 *  3. PRESENCE IS A SEPARATE NODE, addressed by `data-secret-presence`, so the
 *     async `hasSecret` can land into it without repainting -- and without
 *     wiping a key the user is mid-paste. It starts at UNKNOWN, never at "Not
 *     set": view-model.ts rule 2, "telling someone their key is missing while
 *     the keychain lookup is still in flight is how a working key gets pasted
 *     twice".
 */
function secretControls(doc: Document, row: SecretRow, strings: Strings): readonly HTMLElement[] {
  const presence = doc.createElement("span");
  presence.className = "setting-value setting-presence";
  presence.dataset["secretPresence"] = row.key;
  presence.textContent = row.presence;

  const input = doc.createElement("input") as HTMLElement & { type: string; placeholder: string };
  // NOTE: no `input.value = ...` here, ever. See property 1 above.
  input.type = "password";
  input.className = "setting-value setting-input";
  input.setAttribute("aria-label", row.label);
  input.placeholder = strings.secretPlaceholder;
  input.setAttribute("autocomplete", "off");
  input.setAttribute("autocapitalize", "off");
  input.setAttribute("autocorrect", "off");
  input.setAttribute("spellcheck", "false");
  // `change`, like every other field: committed on blur or Enter, so a
  // half-pasted key never reaches the keychain.
  input.dataset["action"] = "set-secret";
  input.dataset["settingKey"] = row.key;

  const clear = doc.createElement("button") as HTMLElement & { type: string };
  clear.type = "button";
  clear.className = "setting-clear";
  clear.textContent = strings.actionClearSecret;
  clear.dataset["action"] = "clear-secret";
  clear.dataset["settingKey"] = row.key;
  // Named for the key it clears. "Remove" alone, repeated once per secret, is
  // a list of identical buttons to anyone navigating by control name.
  clear.setAttribute("aria-label", `${strings.actionClearSecret}: ${row.label}`);

  return [presence, input, clear, settingError(doc, row.key)];
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
  /** Resolved `hasSecret` answers. Empty by default, which paints every secret
   *  as UNKNOWN -- the honest first frame for a screen whose keychain lookups
   *  are async. `refreshSecretPresence` fills the nodes in when they land. */
  secretPresence: SecretPresence = new Map(),
): HTMLElement {
  const section = doc.createElement("section");
  section.className = "screen screen-settings";
  section.append(screenHeading(doc, { name: "settings" }, strings));

  const defByKey = new Map(settings.defs().map((def) => [def.key, def]));

  const view = buildSettings(settings, secretPresence);
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
        // The field and the place its refusal is written, together. The alert
        // node ships empty and hidden rather than being created on the failure
        // -- an alert region inserted at the moment it has something to say is
        // announced unreliably by every screen reader.
        el.append(settingControl(doc, def, row, settings), settingError(doc, row.key));
      } else if (row.kind === "secret") {
        // Editable, at last. This row was a read-only `<span>` reporting
        // "Not set" forever: there was no secret def to render it and, had
        // there been one, no way to fill it in -- which is how the app shipped
        // with an in-process engine and no field to give it a credential.
        el.append(...secretControls(doc, row, strings));
      } else {
        const value = doc.createElement("span");
        value.className = "setting-value";
        value.textContent = String(row.value);
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
    // A DIV wrapping the controls, not a button that IS the row. A delete
    // control has to live inside the row it deletes, and a button inside a
    // button is invalid markup that browsers un-nest -- which puts the delete
    // control somewhere other than where it was written.
    const el = doc.createElement("div");
    el.className = `row row-chat row-chat-${row.kind}`;
    el.dataset["chatId"] = row.id;

    const open = doc.createElement("button");
    open.type = "button";
    open.className = "chat-open";
    // A tap on an unreadable row has nowhere useful to go, so only real chats
    // carry the open-chat intent -- intents.ts refuses a missing chatId anyway.
    if (row.kind === "chat") {
      open.dataset["action"] = "open-chat";
      open.dataset["chatId"] = row.id;
    }
    // Title AND when it was last touched, from one string so the visible time
    // and the spoken time cannot differ. `buildChatList` has computed
    // `updatedLabel` for every row on every visit since it was written and
    // nothing rendered it: the list is SORTED by recency and showed none of
    // it, so two chats called "Untitled" were indistinguishable.
    open.setAttribute(
      "aria-label",
      row.kind === "chat"
        ? strings.chatUpdated(chatRowName(strings, row), row.updatedLabel)
        : chatRowName(strings, row),
    );
    const title = doc.createElement("span");
    title.className = "chat-title";
    title.textContent = row.title;
    open.append(title);
    if (row.kind === "chat") {
      const when = doc.createElement("span");
      when.className = "chat-updated";
      when.textContent = row.updatedLabel;
      open.append(when);
    }
    el.append(open);

    if (row.kind === "chat") {
      // The affordance for `session.remove` -> `repository.remove` ->
      // `storage.remove`. All three were implemented and contract-tested, the
      // `delete-chat` intent was decoded and tested, and NOTHING in the app
      // rendered a control carrying it -- so a conversation, once started,
      // could never be removed from the device by any sequence of taps.
      const del = doc.createElement("button");
      del.type = "button";
      del.className = "chat-delete";
      del.dataset["action"] = "delete-chat";
      del.dataset["chatId"] = row.id;
      // The title is carried on the button itself, not re-derived from the
      // row's text: `parentElement.textContent` folds in the title, the
      // relative time and the button's own word, so arming produced labels
      // like "Delete Trip plan5m agoConfirm". Held here it stays the clean
      // name on every rebuild and arming pass.
      del.dataset["chatTitle"] = row.title;
      del.textContent = strings.actionDelete;
      del.setAttribute("aria-label", strings.deleteChat(row.title));
      el.append(del);
    }
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

  /**
   * The WALL clock, and it comes from the port.
   *
   * `TimePort.epochMs` existed, was implemented by the web adapter, was
   * conformance-tested, and had zero callers anywhere in the application: every
   * wall-clock read in this file was a bare `Date.now()`, so the seam that is
   * supposed to make time injectable ran past its own port. The port draws the
   * distinction in its doc comment -- `nowMs` is monotonic and for elapsed
   * intervals, `epochMs` is the wall clock and for timestamps -- and "conflating
   * them is how a clock correction mid-stream makes a coalescer wait forever or
   * flush every frame".
   */
  const nowEpochMs = deps.now ?? ((): number => platform.time.epochMs());

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
      // MONOTONIC, not the wall clock. `announce` compares
      // `nowMs - lastStreamAtMs` against its rate-limit interval, and a
      // `Date.now()` there is exactly the conflation `core/src/ports/time.ts`
      // is written against: an NTP correction that moves the clock backwards
      // mid-answer silences every further streaming announcement until real
      // time catches up with the pre-correction reading, so a screen-reader
      // user simply stops being told what the model is saying.
      nowMs: platform.time.nowMs(),
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
    engines: (persistence, history, settings, onIgnored) =>
      appEngines({
        settings,
        http: platform.http,
        // The FULL port, straight from the platform. `createApp` hands this
        // factory the settings FACADE, which deliberately cannot read a
        // secret; the engine needs the value, so it gets the port here, in
        // the one file allowed to name a concrete adapter.
        secrets: platform.secrets,
        persistence,
        // Read side and write side, both from the session `createApp` just
        // built. A turn is recorded through one and replayed through the
        // other, so the model's memory and the transcript on screen cannot
        // drift apart.
        history,
        onIgnored,
        ...(deps.loadAgent === undefined ? {} : { loadAgent: deps.loadAgent }),
      }),
    // The platform's defs, so the engine Settings shows as the default and the
    // engine that answers a first launch are the same one.
    settingDefs: settingDefsFor(platform.kind),
    // The default when settings name none, chosen by platform: the in-process
    // engine on a device (a phone has no `127.0.0.1:8765` to reach, and a
    // cleartext localhost address is refused by iOS ATS and Android), the
    // remote engine on the web where a server is what there is. createApp
    // prefers the persisted `engineId` over this, so it only decides the
    // first launch. registry.ts says why desktop Tauri counts as a device.
    engineId: defaultEngineIdFor(platform.kind),
    onPublish: publish,
    now: nowEpochMs,
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
    // The four EFFECTIVE insets, on the container every screen lives in.
    //
    // app.css declares `--inset-*` as `var(--safe-area-inset-*)` so the first
    // paint has something, and every layout rule consumes `--inset-*` rather
    // than the env() mirror. This is why: on Android `env(safe-area-inset-*)`
    // is the DISPLAY CUTOUT and nothing else -- measured on an Android 15
    // emulator with no cutout configured, `--safe-area-inset-top` was 0px
    // against a 24px status bar and 24px navigation bar, and the topbar's title
    // was painted straight through the clock. `shell.insets` is the OS's own
    // numbers (MainActivity.kt feeds them in through the bridge in
    // adapters/src/tauri/shell.ts), so writing them here is what makes the
    // stylesheet see a status bar at all.
    //
    // Written on `root`, not on `screen`: settings and chats are SIBLINGS of
    // the chat screen, so anything set on `screen` never reaches them -- which
    // is the shape the original `--inset-top` had, and it was consumed by no
    // rule at all.
    //
    // The env() mirror is deliberately NOT overwritten. It is what
    // `readInsets` reads, and writing our own value back into the variable we
    // read from would make the shell echo itself instead of the device.
    const insets = layout.insets;
    root.style.setProperty("--inset-top", `${insets.top}px`);
    root.style.setProperty("--inset-right", `${insets.right}px`);
    root.style.setProperty("--inset-bottom", `${insets.bottom}px`);
    root.style.setProperty("--inset-left", `${insets.left}px`);
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

  /** Every element under `scope`, including `scope` itself. The same walk
   *  `syncSettings` and `byFocusId` do: there is no `querySelectorAll` in the
   *  seam a test drives, and the tree is a settings screen, not a document. */
  const everyElement = (scope: HTMLElement): readonly HTMLElement[] => {
    const found: HTMLElement[] = [];
    const stack: HTMLElement[] = [scope];
    while (stack.length > 0) {
      const node = stack.pop();
      if (node === undefined) break;
      found.push(node);
      for (const child of node.children) {
        if (child instanceof HTMLElement) stack.push(child);
      }
    }
    return found;
  };

  /**
   * Put a secret row back the way it must always look: field EMPTY, and the
   * refusal for this key shown or cleared.
   *
   * Emptying is the point, and it is not cosmetic. `syncSettings` redraws a
   * plain field from the store, which is the honest thing for an engine
   * address; the mirror of that for a secret would mean reading it back, and
   * there is deliberately nothing to read it back WITH. So the field returns
   * to empty -- the value the user pasted lives in the keychain and stops
   * existing in the DOM, where the next screenshot, crash report or
   * accessibility dump would otherwise find it.
   */
  const syncSecret = (key: string, refusal: string | null): void => {
    for (const node of everyElement(root)) {
      if (node.dataset["action"] === "set-secret" && node.dataset["settingKey"] === key) {
        (node as HTMLElement & { value: string }).value = "";
        continue;
      }
      if (node.dataset["settingError"] !== key) continue;
      node.textContent = refusal ?? "";
      node.hidden = refusal === null;
    }
  };

  /**
   * Resolve `hasSecret` for every secret def and write the answer into the
   * row's presence node.
   *
   * PRESENCE, not the value: `hasSecret` is the method that exists so a screen
   * can say "Configured" without faulting a key into memory (ports/secrets.ts
   * rule 2), and this is the only place the app asks.
   *
   * Async and separate from the paint because `buildSettings` is synchronous
   * and a keychain lookup is not. Writing into an existing node rather than
   * rebuilding the screen is what keeps a half-pasted key in the field when
   * the answer lands a moment later.
   */
  // Which presence lookup is the most recent one asked for. A save followed by
  // a Remove fires two overlapping walks, and with a native keychain adapter
  // (the declared next step) `hasSecret` can resolve OUT OF ORDER -- the older
  // lookup landing last would paint "Configured" over a row the user just
  // cleared, or "Not set" over one they just saved. Only the latest request is
  // allowed to write; a stale one has already been superseded and is dropped.
  let latestPresenceSeq = 0;
  const refreshSecretPresence = (scope: HTMLElement): void => {
    const seq = ++latestPresenceSeq;
    void (async (): Promise<void> => {
      const answers = new Map<string, string>();
      for (const def of app.settings.defs()) {
        const ref = secretRefOf(def);
        if (ref === null) continue;
        answers.set(def.key, presenceLabel((await app.settings.hasSecret(ref)) ? "configured" : "not-set"));
      }
      // A newer refresh started while this one awaited: its answer is the
      // current truth, so this one must not overwrite it.
      if (seq !== latestPresenceSeq) return;
      for (const node of everyElement(scope)) {
        const key = node.dataset["secretPresence"];
        if (key === undefined) continue;
        const label = answers.get(key);
        if (label !== undefined) node.textContent = label;
      }
    })().catch(() => {
      // A keychain that will not answer leaves the row at UNKNOWN, which is
      // what it already says. Overwriting it with "Not set" would tell someone
      // their key is gone because a lookup failed -- view-model.ts rule 2, and
      // the reason UNKNOWN is a state at all. A floating rejection here would
      // also reach the global crash handler and replace the whole app.
    });
  };

  // ---- screens the router drives -----------------------------------------
  // The chat screen is retained (it holds scroll position and a live stream);
  // settings and chats are built on demand and rebuilt each visit. `transition`
  // decides what to mount, hide and destroy; this half only obeys it.
  /**
   * Redraw a chats section from storage, in place.
   *
   * Extracted from the `build` callback because a DELETE has to refresh a list
   * that is already on screen: the chats screen is rebuilt on each VISIT, and
   * deleting a row is not a visit. Rebuilding through the same function is
   * what keeps "the row is gone" and "the list is now empty" the same
   * rendering -- removing the node by hand would leave a list showing nothing
   * where `chatsEmpty` belongs.
   */
  const refreshChats = async (section: HTMLElement): Promise<void> => {
    try {
      const [summaries, unreadable] = await Promise.all([
        app.session.list(),
        app.session.repository.listUnreadable(),
      ]);
      const fresh = buildChatsScreen(
        doc,
        summaries as readonly ChatSummary[],
        unreadable,
        nowEpochMs(),
        strings,
      );
      section.textContent = "";
      for (const child of [...fresh.children]) section.append(child as HTMLElement);
    } catch {
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
    }
  };

  const screens = createScreens({
    root,
    build: (id: ScreenId): HTMLElement => {
      if (id === "settings") {
        const section = buildSettingsScreen(doc, app.settings, strings);
        // Built with presence UNKNOWN, then filled in. The alternative --
        // awaiting the keychain before painting -- is a blank screen for as
        // long as the platform takes to answer, and `build` is synchronous
        // because `transition` is.
        refreshSecretPresence(section);
        return section;
      }
      if (id === "chats") {
        // A fresh snapshot each visit: a chat created since the list was last
        // seen must appear, and one deleted must be gone.
        const section = buildChatsScreen(doc, [], [], nowEpochMs(), strings);
        void refreshChats(section);
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

  /**
   * The chat whose delete control is ARMED, or null.
   *
   * Deleting a conversation is the only irreversible thing in this app, and a
   * chat row's delete button sits a few millimetres from the row that opens
   * it, on a touch screen. So the first tap arms and the second deletes.
   *
   * Held by chat id rather than by element, for the same reason `syncSettings`
   * walks: the chats screen is rebuilt on every visit, so any element held
   * across a navigation is detached.
   */
  let armedDelete: string | null = null;

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
    // Leaving the list disarms it. A delete armed before a navigation and
    // still armed on the way back would turn the FIRST tap after returning
    // into a deletion, with nothing on screen saying so -- the two-tap guard
    // silently spending itself while the user was elsewhere.
    armedDelete = null;
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
  /** The tags that HOLD a value. Checked by tag rather than by reading
   *  `node.value` on everything, because `Actionable.value` being ABSENT is
   *  what tells intents.ts "this element is not a field" -- and a `<div>` in
   *  the fake DOM reports `""`, which would read as a cleared setting. */
  const FIELD_TAGS = new Set(["INPUT", "SELECT", "TEXTAREA"]);

  const chainOf = (target: EventTarget | null): Actionable[] => {
    const chain: Actionable[] = [];
    let node = target instanceof Element ? target : null;
    while (node !== null) {
      if (node instanceof HTMLElement) {
        const value = (node as HTMLElement & { value?: unknown }).value;
        chain.push({
          dataset: { ...node.dataset },
          ...(node instanceof HTMLButtonElement ? { disabled: node.disabled } : {}),
          ...(FIELD_TAGS.has(node.tagName) && typeof value === "string" ? { value } : {}),
        });
      }
      node = node.parentElement;
    }
    return chain;
  };

  /**
   * Put every settings field back in step with the STORE, and show or clear
   * the refusal for one key.
   *
   * A walk rather than a captured element, for two reasons. The settings
   * screen is rebuilt on every visit (`screens.build`), so any reference held
   * across a navigation points at a detached node. And a `set` the store
   * ACCEPTS can still store something other than what was typed -- a def's
   * `validate` may clamp -- so the honest thing after any write, accepted or
   * refused, is to redraw the fields from what is actually stored rather than
   * to leave the typed text on screen.
   */
  const syncSettings = (key: string, refusal: string | null): void => {
    const defs = new Map(app.settings.defs().map((d) => [d.key, d]));
    const stack: HTMLElement[] = [root];
    while (stack.length > 0) {
      const node = stack.pop();
      if (node === undefined) break;
      for (const child of node.children) {
        if (child instanceof HTMLElement) stack.push(child);
      }
      if (node.dataset["action"] === "set-setting") {
        const def = defs.get(node.dataset["settingKey"] ?? "");
        if (def !== undefined) {
          (node as HTMLElement & { value: string }).value = String(
            app.settings.get(def.key) ?? def.default,
          );
        }
        continue;
      }
      const errorFor = node.dataset["settingError"];
      if (errorFor === undefined) continue;
      // Only this key's note is touched. Clearing them all would wipe a
      // refusal the user has not read off a DIFFERENT setting; leaving them
      // all would keep accusing a write that has since succeeded.
      if (errorFor !== key) continue;
      node.textContent = refusal ?? "";
      node.hidden = refusal === null;
    }
  };

  /** Put every delete control in step with `armedDelete`. */
  const syncDeleteArming = (): void => {
    const stack: HTMLElement[] = [root];
    while (stack.length > 0) {
      const node = stack.pop();
      if (node === undefined) break;
      for (const child of node.children) {
        if (child instanceof HTMLElement) stack.push(child);
      }
      if (node.dataset["action"] !== "delete-chat") continue;
      const id = node.dataset["chatId"] ?? "";
      // The clean title is carried on the button's own dataset, set when the
      // row was built. Reading `parentElement.textContent` instead folded in
      // the visible time and the button's own word ("Delete Trip plan5m
      // agoConfirm"); the dataset holds the name the row was rendered with.
      const title = node.dataset["chatTitle"] ?? id;
      const armed = id !== "" && id === armedDelete;
      node.textContent = armed ? strings.actionConfirmDelete : strings.actionDelete;
      node.setAttribute("aria-label", armed ? strings.deleteChatConfirm(title) : strings.deleteChat(title));
      node.dataset["armed"] = armed ? "true" : "false";
    }
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
      case "set-setting": {
        // The def is looked up from the LIVE facade, not from `SETTING_DEFS`,
        // so this cannot drift from what the screen was rendered off. An
        // unknown key means the DOM and the registry disagree -- refuse it
        // rather than write it: `set` would refuse anyway, silently.
        const def = app.settings.defs().find((d) => d.key === intent.key);
        if (def === undefined) return;
        // `validateInput` first, so an unparseable value never reaches `set`
        // where the refusal comes back as a bare `false` with no reason.
        const validated = validateInput(def, intent.raw);
        let stored = false;
        if (validated !== null) {
          try {
            stored = await app.settings.set(intent.key, validated);
          } catch {
            // `set` persists through StoragePort, which REJECTS on a real
            // device (SecurityError with site data blocked, QuotaExceededError
            // under storage pressure). Left to float, that rejection reaches
            // the global crash handler and replaces the WHOLE app with the
            // fatal screen. A failed settings write must stay local -- and it
            // is a refusal like any other, so it is said rather than swallowed.
            stored = false;
          }
        }
        // Said, not merely undone. A field that snaps back in silence is
        // indistinguishable from a mis-tap or from a save that worked, and on
        // this screen that leaves someone re-typing the same refused value.
        const refusal = stored ? null : strings.settingRejected(labelOf(def));
        if (refusal !== null) assertive.textContent = refusal;
        syncSettings(intent.key, refusal);
        return;
      }
      case "delete-chat": {
        // `session.remove` -> `repository.remove` -> `storage.remove`: three
        // implemented, contract-tested methods with no caller in the app, and
        // an intent `intents.ts` decoded for a control nothing rendered. A
        // conversation, once started, could not be removed from the device.
        //
        // The title is a nicety for the announcement; `session.list` reads
        // StoragePort, which REJECTS on a real device (SecurityError with site
        // data blocked, QuotaExceededError). These reads sit OUTSIDE the remove
        // try below, and `perform` is invoked through a floating `void`, so a
        // rejection here floats to the global crash handler and replaces the
        // whole app with the fatal screen for a lookup that only decides a
        // label. Degrade to the id rather than crash.
        const titleOf = async (): Promise<string> => {
          try {
            return (
              (await app.session.list()).find((c) => c.id === intent.chatId)?.title ??
              intent.chatId
            );
          } catch {
            return intent.chatId;
          }
        };
        // Arm first. The second tap on the SAME row is the one that deletes;
        // a tap on a different row moves the arming rather than deleting two.
        if (armedDelete !== intent.chatId) {
          armedDelete = intent.chatId;
          syncDeleteArming();
          assertive.textContent = strings.deleteChatConfirm(await titleOf());
          return;
        }
        const title = await titleOf();
        armedDelete = null;
        // Read BEFORE the remove. `session.remove` clears `current` itself
        // when it deletes the open chat, so asking afterwards always answers
        // null and the transcript is left on screen -- a conversation the user
        // can keep typing into that no longer exists on disk.
        const wasOpen = app.session.current()?.id === intent.chatId;
        try {
          await app.session.remove(intent.chatId);
        } catch {
          // StoragePort rejects on a real device. Left to float this reaches
          // the crash handler and replaces the whole app; and a delete that
          // silently did nothing leaves the user believing it worked.
          assertive.textContent = strings.chatDeleteFailed;
          syncDeleteArming();
          return;
        }
        // The conversation on screen may be the one just deleted. Leaving it
        // there is a transcript the user can keep typing into that no longer
        // exists on disk -- the next turn would silently re-create it.
        if (wasOpen) {
          void app.controller.stop();
          app.controller.setChat(mintChatId());
          app.session.reset();
          history = [];
          render = emptyRender;
          nodes.nodes.clear();
          announcer = initialAnnouncer;
          transcript.textContent = "";
          polite.textContent = "";
        }
        assertive.textContent = strings.chatDeleted(title);
        const list = screens.nodes.get("chats");
        if (list !== undefined) await refreshChats(list);
        return;
      }
      case "set-secret": {
        // The def comes from the LIVE facade for the same reason `set-setting`
        // does: the screen and the registry must not be able to disagree about
        // which key this field belongs to.
        const def = app.settings.defs().find((d) => d.key === intent.key);
        if (def === undefined) return;
        // `secretRefOf` refuses a def that is not a secret, and a secret def
        // with nowhere to write. Either would otherwise end with a pasted key
        // going somewhere nobody chose.
        const ref = secretRefOf(def);
        let stored = false;
        if (ref !== null) {
          try {
            // Trimmed: a key pasted from a mail client or a terminal arrives
            // with a trailing newline, and an `Authorization` header built
            // from it fails with an error about the key rather than about the
            // whitespace. No provider key contains one.
            await app.settings.setSecret(ref, intent.raw.trim());
            stored = true;
          } catch {
            // SecretsPort rejects on a real device -- a locked keychain, a
            // keystore that will not open. Left to float this reaches the
            // global crash handler and replaces the WHOLE app with the fatal
            // screen, on the one screen the user is trying to repair.
            stored = false;
          }
        }
        const refusal = stored ? null : strings.settingRejected(labelOf(def));
        // The LABEL, never the value: this is an assertive live region and it
        // is read out loud.
        assertive.textContent = stored ? strings.secretStored(labelOf(def)) : (refusal ?? "");
        syncSecret(intent.key, refusal);
        // Presence has changed; ask again rather than assuming. `setSecret`
        // resolving is not proof the store kept it.
        refreshSecretPresence(root);
        return;
      }
      case "clear-secret": {
        const def = app.settings.defs().find((d) => d.key === intent.key);
        if (def === undefined) return;
        const ref = secretRefOf(def);
        let cleared = false;
        if (ref !== null) {
          try {
            await app.settings.clearSecret(ref);
            cleared = true;
          } catch {
            cleared = false;
          }
        }
        const refusal = cleared ? null : strings.settingRejected(labelOf(def));
        assertive.textContent = cleared ? strings.secretCleared(labelOf(def)) : (refusal ?? "");
        syncSecret(intent.key, refusal);
        refreshSecretPresence(root);
        return;
      }
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

  // Committing a field is delegated on ROOT for the same reason a tap is: the
  // settings screen is rebuilt on every visit, so a listener attached to a
  // field belongs to a node that is thrown away on the next navigation. No
  // `preventDefault` -- `change` has no default action to cancel, and the
  // composer's textarea carries no `data-action`, so `intentFrom` refuses it.
  root.addEventListener("change", (event) => {
    const intent = intentFrom(chainOf(event.target));
    if (intent === null) return;
    void perform(intent);
  });

  return app;
}

// Auto-mount when loaded as a page, never when imported by a test.
const el = globalThis.document?.getElementById("root");
if (el !== null && el !== undefined) {
  void mount({ root: el });
}
