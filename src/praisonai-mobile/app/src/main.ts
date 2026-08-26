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
import { enginesFor, OPENAI_KEY, SETTING_DEFS } from "./registry.ts";
import { intentFrom, type Actionable, type Intent } from "./intents.ts";
import { applyOps, emptyNodes, type RowNodes } from "./dom.ts";
import { installCrashHandler } from "./crash.ts";
import { emptyRender, reconcile, type RenderState } from "../../ui/src/render/reconcile.ts";
import { buildTranscript } from "../../ui/src/transcript/view-model.ts";
import type { RunView } from "../../core/src/run/controller.ts";
import type { Route } from "../../ui/src/router.ts";

/**
 * Every user-visible string, injected.
 *
 * Not hardcoded at the render site, which is where they all were: an audit
 * found every one of them inline and no locale plumbing anywhere. Passing them
 * in means the English table is one object and a translated one is another,
 * and this file never has to change to gain a language.
 */
export interface AppStrings {
  readonly appName: string;
  readonly newChat: string;
  readonly send: string;
  readonly stop: string;
  readonly settings: string;
  readonly emptyChats: string;
  readonly emptyTranscript: string;
  readonly bootFailed: (detail: string) => string;
  readonly crashed: string;
}

export const EN: AppStrings = {
  appName: "PraisonAI",
  newChat: "New chat",
  send: "Send",
  stop: "Stop",
  settings: "Settings",
  emptyChats: "No conversations yet.",
  emptyTranscript: "Ask something to begin.",
  bootFailed: (detail) => `PraisonAI could not start: ${detail}`,
  crashed: "Something went wrong. Your conversations are saved.",
};

export interface MountDeps {
  readonly root: HTMLElement;
  readonly platform?: Platform;
  readonly strings?: AppStrings;
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

export async function mount(deps: MountDeps): Promise<App | null> {
  const strings = deps.strings ?? EN;
  const root = deps.root;
  const doc = root.ownerDocument;
  const platform = deps.platform ?? detectPlatform();

  // Installed BEFORE anything else can throw. A crash during boot with no
  // handler is a blank page and a silent console on a device nobody can attach
  // a debugger to.
  const owner = doc.defaultView;
  installCrashHandler({
    ...(owner === null ? {} : { view: owner }),
    onCrash: () => renderFatal(root, strings.crashed),
  });

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
  toSettings.textContent = strings.settings;
  bar.append(title, newChat, toSettings);

  const transcript = doc.createElement("main");
  transcript.className = "transcript";
  // The stream lands here, so a screen reader is told politely rather than
  // interrupted on every token.
  transcript.setAttribute("role", "log");
  transcript.setAttribute("aria-live", "polite");
  transcript.setAttribute("aria-label", strings.appName);

  const composer = doc.createElement("form");
  composer.className = "composer";
  const input = doc.createElement("textarea");
  input.rows = 1;
  input.setAttribute("aria-label", strings.send);
  const sendButton = doc.createElement("button");
  sendButton.type = "submit";
  sendButton.dataset["action"] = "send";
  sendButton.dataset["variant"] = "primary";
  sendButton.textContent = strings.send;
  composer.append(input, sendButton);

  screen.append(bar, transcript, composer);
  root.textContent = "";
  root.append(screen);

  // ---- boot ---------------------------------------------------------------
  let render: RenderState = emptyRender;
  const nodes: RowNodes = emptyNodes();

  const publish = (view: RunView): void => {
    const built = buildTranscript(view.turn, view.approvals);
    const diff = reconcile(render, built.rows);
    applyOps(transcript, nodes, diff.ops);
    render = diff.next;
    sendButton.textContent = view.turn.phase === "streaming" ? strings.stop : strings.send;
    sendButton.dataset["action"] = view.turn.phase === "streaming" ? "stop" : "send";
  };

  const booted = await createApp({
    storage: platform.storage,
    secrets: platform.secrets,
    time: platform.time,
    shell: platform.shell,
    engines: enginesFor({ settings: facadeStub(), http: platform.http }),
    settingDefs: SETTING_DEFS,
    engineId: "remote-http",
    onPublish: publish,
    now: deps.now ?? (() => Date.now()),
    newChatId: deps.newChatId ?? (() => globalThis.crypto.randomUUID()),
  });

  if (!booted.ok) {
    // A named failure, on screen. `app/src/engines.ts` promises exactly this
    // and nothing rendered it: an unusable engine used to be an unhandled
    // branch that left a blank page.
    renderFatal(root, strings.bootFailed(booted.detail));
    return null;
  }

  const app = booted.app;

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
      case "stop":
        await app.controller.stop();
        return;
      case "approve":
        await app.controller.decide(intent.approvalId, intent.choice);
        return;
      case "new-chat":
        app.session.reset();
        render = emptyRender;
        nodes.nodes.clear();
        transcript.textContent = "";
        return;
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

/** A settings facade before settings exist, used only to build the engine
 *  list at boot. Replaced by the real one immediately after. */
function facadeStub() {
  return {
    get: () => undefined,
    set: async () => false,
    defs: () => SETTING_DEFS,
    subscribe: () => () => {},
    hasSecret: async () => false,
    setSecret: async () => {},
    clearSecret: async () => {},
    secretsAreHardwareBacked: false,
  };
}

// Auto-mount when loaded as a page, never when imported by a test.
const el = globalThis.document?.getElementById("root");
if (el !== null && el !== undefined) {
  void mount({ root: el });
}

export { OPENAI_KEY };
