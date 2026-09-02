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
import { buildTranscript } from "../../ui/src/transcript/view-model.ts";
import type { RunView } from "../../core/src/run/controller.ts";
import type { Route } from "../../ui/src/router.ts";
import { en, type Strings } from "../../ui/src/i18n/strings.ts";
import { announce, initialAnnouncer, type AnnouncerState } from "../../ui/src/a11y/announce.ts";
import type { EngineChoice } from "./engines.ts";
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";
import { createPraisonTsEngine, type RunPersistence } from "../../engines/src/praisonai-ts/engine.ts";
import type { PraisonAgent } from "../../engines/src/praisonai-ts/agent-api.ts";
import type { SettingsFacade } from "../../core/src/settings/store.ts";
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

  // ---- the frame the app paints into -------------------------------------
  const screen = doc.createElement("div");
  screen.className = "screen";

  const bar = doc.createElement("header");
  bar.className = "topbar";
  const title = doc.createElement("h1");
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
  bar.append(title, newChat, toSettings);

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

  screen.append(bar, transcript, composer, polite, assertive);
  root.textContent = "";
  root.append(screen);

  // ---- boot ---------------------------------------------------------------
  let render: RenderState = emptyRender;
  const nodes: RowNodes = emptyNodes();
  let announcer: AnnouncerState = initialAnnouncer;

  const publish = (view: RunView): void => {
    const built = buildTranscript(view.turn, view.approvals);
    const diff = reconcile(render, built.rows);
    applyOps(transcript, nodes, diff.ops, strings);
    render = diff.next;

    // Coalesced to finished sentences and rate-limited: announcing every token
    // is unusable, announcing nothing makes the app opaque.
    const spoken = announce(announcer, {
      turn: view.turn,
      strings,
      locale: "en",
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

    sendButton.textContent = view.turn.phase === "streaming" ? strings.actionStop : strings.actionSend;
    sendButton.dataset["action"] = view.turn.phase === "streaming" ? "stop" : "send";
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
  const applyGeometry = (): void => {
    const insets = platform.shell.insets;
    screen.style.setProperty("--keyboard-height", `${platform.shell.keyboardHeightPx}px`);
    screen.style.setProperty("--inset-top", `${insets.top}px`);
  };
  applyGeometry();
  platform.shell.onInsetsChanged(applyGeometry);
  platform.shell.onKeyboardHeightChanged(applyGeometry);

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
      default:
        return;
    }
  };

  const submit = async (): Promise<void> => {
    const text = input.value.trim();
    if (text === "") return; // an empty send is a no-op, not an empty turn
    input.value = "";
    await app.controller.send(text);
  };

  composer.addEventListener("submit", (event) => {
    event.preventDefault();
    void submit();
  });

  screen.addEventListener("click", (event) => {
    const intent = intentFrom(chainOf(event.target));
    if (intent === null) return;
    event.preventDefault();
    void perform(intent);
  });

  return app;
}

// Auto-mount when loaded as a page, never when imported by a test.
const el = globalThis.document?.getElementById("root");
if (el !== null && el !== undefined) {
  void mount({ root: el });
}
