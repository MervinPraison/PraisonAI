/**
 * The entry point's one decision a test can reach.
 *
 * `mount` needs a whole fake SSE transport to drive end to end, so the parts
 * of it that can be wrong are extracted and called directly instead.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { stopNotice } from "./main.ts";
import { defaultEngineIdFor } from "./registry.ts";
import { en } from "../../ui/src/i18n/strings.ts";

test("a device's first-launch default is the in-process engine; the web's is remote", () => {
  // A phone cannot reach `http://127.0.0.1:8765`, and the cleartext localhost
  // address is refused by iOS ATS and Android -- so a remote default on a
  // device was a first prompt that failed with a status code. The in-process
  // engine ships as a lazy chunk beside app.js now, so it is the one choice
  // that works with nothing configured, and the picker offers it. The web
  // keeps the remote engine: a server is what a browser tab has.
  // `Platform["kind"]` cannot tell desktop Tauri (`cargo tauri dev`) from a
  // phone, so desktop starts in-process too and switches in Settings.
  assert.equal(defaultEngineIdFor("tauri"), ENGINE_PRAISONAI_TS);
  assert.equal(defaultEngineIdFor("web"), ENGINE_REMOTE_HTTP);
});

test("a stop the engine REFUSED is announced", () => {
  // Discarding the controller's boolean made a refused Stop indistinguishable
  // from an accepted one: the button label flips off `turn.phase`, which
  // settles either way, while the run keeps generating and keeps billing.
  assert.equal(stopNotice(false, en), en.stopRefused);
});

test("a stop the engine ACCEPTED says nothing", () => {
  // The pair. Announcing unconditionally would tell the user every successful
  // Stop had failed, which is the same defect pointed the other way.
  assert.equal(stopNotice(true, en), null);
});

test("the refusal text says the run may still be going", () => {
  // The point of saying anything at all: the user's next action depends on
  // whether the work stopped, so "it did not stop" has to be in the sentence.
  assert.match(en.stopRefused, /still be running/i);
});

// ---- the composition root, driven end to end --------------------------------
//
// Everything below needed a fake DOM, which is why none of it existed. A
// round-four audit drove `mount()` with one and found six defects here, all of
// the same shape: a pure function that is correct, and a composition root that
// calls it wrongly or not at all.

import { createFakeDom } from "../../testing/src/fake-dom.ts";
import { createFakeShell, PHONE_INSETS } from "../../testing/src/fake-shell.ts";
import { createFakeStorage } from "../../testing/src/fake-storage.ts";
import { createFakeSecrets } from "../../testing/src/fake-secrets.ts";
import { createFakeHttp, sseResponse, streamOf } from "../../testing/src/fake-http.ts";
import { PROTOCOL_VERSION } from "../../protocol/src/version.ts";
import { appEngines, mount, EMPTY_TITLE_ID } from "./main.ts";
import { ENGINE_PRAISONAI_TS, ENGINE_REMOTE_HTTP, SETTING_DEFS } from "./registry.ts";
import { createSettingsStore, facadeFor, type SettingsFacade } from "../../core/src/settings/store.ts";
import type { Platform } from "./platform.ts";

test("the real composition root offers the in-process engine", async () => {
  // The package's headline capability -- running the agent loop in-process is
  // the reason praisonai-mobile exists -- and nothing asserted `main.ts` offers
  // it. `enginesFor` only pushes it when `createInProcess` is supplied, and the
  // composition root did not supply one, so the whole of engines/praisonai-ts/
  // was unreachable from the application while its own suite stayed green
  // (every test that exercises it constructs it directly).
  const secrets = createFakeSecrets();
  const store = createSettingsStore(SETTING_DEFS, createFakeStorage(), secrets);
  await store.load();
  const settings: SettingsFacade = facadeFor(store, secrets);
  const persistence = {
    async record() {
      return { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
  };
  const conversation = { messages: () => [] };

  const ids = appEngines({
    settings,
    http: createFakeHttp(),
    secrets,
    persistence,
    history: conversation,
    onIgnored: () => {},
  }).map((c) => c.id);

  assert.ok(ids.includes(ENGINE_PRAISONAI_TS), `only ${ids.join(", ")} on offer`);
  // And the remote engine is still offered and first, so the default keeps
  // working with nothing configured.
  assert.equal(ids[0], ENGINE_REMOTE_HTTP, "the remote engine must stay the default");
});

test("the in-process engine, when its chunk cannot load, fails RECOVERABLY", async () => {
  // The engine reaches praisonai through a lazily-fetched chunk, and a fetch
  // can fail: a flaky connection, a build that left the engine out, a hashed
  // file the page no longer matches. This used to be exercised by the module's
  // ABSENCE from disk; with praisonai installed the real loader succeeds here
  // (and would go to the network), so the failing loader is INJECTED, through
  // the seam appEngines exposes for exactly this. Constructing the engine must
  // still succeed (create() opens no upstream), and the failure must arrive as
  // a single recoverable `error` event through engine.ts's run loop, never as
  // an unhandled rejection that takes down the turn opaquely. That is the
  // named, on-screen failure engines.ts argues for.
  const secrets = createFakeSecrets();
  const store = createSettingsStore(SETTING_DEFS, createFakeStorage(), secrets);
  await store.load();
  const settings: SettingsFacade = facadeFor(store, secrets);
  const persistence = {
    async record() {
      return { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
  };
  const conversation = { messages: () => [] };

  const inProcess = appEngines({
    settings,
    http: createFakeHttp(),
    secrets,
    persistence,
    history: conversation,
    onIgnored: () => {},
    loadAgent: async () => {
      throw new Error("chunk-XXXXXXXX.js: failed to fetch");
    },
  }).find((c) => c.id === ENGINE_PRAISONAI_TS);
  assert.ok(inProcess, "the in-process engine must be on offer to be exercised");

  // create() itself must not throw: it wires a factory, it does not load it.
  const engine = await inProcess.create();
  assert.equal(engine.id, ENGINE_PRAISONAI_TS);

  const request = {
    prompt: "hello",
    chatId: "c1",
    runId: "r1",
    tools: false,
    regenerateOf: null,
    attachments: [],
  };
  const seen: string[] = [];
  for await (const event of engine.run(request, new AbortController().signal)) {
    seen.push(event.type);
  }
  await engine.dispose();

  // start then a single error -- the recoverable, named terminal, not a crash.
  assert.deepEqual(seen, ["start", "error"], `expected a recoverable failure, saw ${seen.join(", ")}`);
});

const nodeTime = () => ({
  nowMs: () => performance.now(),
  epochMs: () => Date.now(),
  createScheduler: () => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    return {
      requestFrame: (cb: () => void) => void setImmediate(cb),
      setTimer: (cb: () => void, ms: number) => { timer = setTimeout(cb, ms); timer.unref?.(); },
      clearTimer: () => { if (timer !== null) clearTimeout(timer); timer = null; },
    };
  },
  every: (ms: number, cb: () => void) => {
    const handle = setInterval(cb, ms);
    handle.unref?.();
    return () => clearInterval(handle);
  },
});

const sse = (frames: readonly (readonly [string, unknown])[]): string =>
  frames.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");

const settle = async (ms = 60): Promise<void> => {
  await new Promise((r) => setTimeout(r, ms));
};

function harness(over: { storage?: ReturnType<typeof createFakeStorage> } = {}) {
  const dom = createFakeDom();
  const http = createFakeHttp();
  const storage = over.storage ?? createFakeStorage();
  // Returned as well as installed: the secret tests below have to look INSIDE
  // the keychain to prove a pasted key landed there, and `reads` is what proves
  // the settings screen asked for presence rather than for the value.
  const secrets = createFakeSecrets();
  const platform: Platform = {
    shell: createFakeShell(PHONE_INSETS),
    storage,
    secrets,
    http,
    time: nodeTime(),
    kind: "web",
  };
  return { dom, http, storage, secrets, platform };
}

/** The API key field on the settings screen, by its accessible name. */
const keyField = (dom: ReturnType<typeof createFakeDom>) =>
  dom.find((n) => n.tagName === "INPUT" && n.getAttribute("aria-label") === "OpenAI API key");

/** The presence word for a secret row ("Configured" / "Not set" / UNKNOWN). */
const presenceOf = (dom: ReturnType<typeof createFakeDom>, key: string) =>
  dom.find((n) => n.dataset["secretPresence"] === key)?.textContent ?? null;


const submit = (dom: ReturnType<typeof createFakeDom>, text: string): void => {
  const box = dom.find((n) => n.tagName === "TEXTAREA");
  const form = dom.find((n) => n.tagName === "FORM");
  if (box !== null) box.value = text;
  form?.dispatch("submit", { preventDefault: () => {} });
};

test("a failure before the first token says WHAT failed, not that nothing came back", async () => {
  // The reducer dropped any event arriving before `start`, so the engine's
  // synthesised error was thrown away and `finish()` substituted
  // kind: "empty". 401, 403, 500, 502, offline and a wrong baseUrl all
  // rendered identically as "the engine produced no output", plus a dropped
  // row accusing the engine of sending an event before the turn began.
  //
  // The default baseUrl is 127.0.0.1:8765, which ON A PHONE is the phone
  // itself -- so this was the first thing every new user saw. It also made the
  // auth -> "go to settings" recovery unreachable: the one distinction between
  // "retry this" and "fix your credentials" never survived to the view model.
  for (const [status, wantRecovery] of [[401, "settings"], [403, "settings"], [502, "retry"]] as const) {
    const { dom, http, platform } = harness();
    http.on("/chat", () => ({ status, headers: {}, body: null }));
    const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

    submit(dom, "hello");
    await settle();

    const errorRow = dom.find((n) => n.className.includes("row-error"));
    assert.ok(errorRow, `HTTP ${status}: no error row rendered`);
    assert.match(errorRow.textContent, /\d\d\d/, "the message should name the status");
    assert.equal(errorRow.dataset["recovery"], wantRecovery, `HTTP ${status} recovery`);
    assert.equal(
      dom.find((n) => n.className.includes("row-dropped")),
      null,
      "a real error must not also be reported as an unreadable frame",
    );
    app?.dispose();
  }
});

test("every polite announcement of a publish is spoken, not just the last", async () => {
  // `region.textContent = item.text` in a loop overwrote the earlier items in
  // the same task. A short answer completing inside one interval produced
  // [polite "<the answer>", polite "Response complete"], so a screen-reader
  // user heard ONLY "Response complete." That is exactly what announce.ts
  // rule 4 exists to prevent, reintroduced where the pure function meets
  // the DOM.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "The capital of France is Paris." }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "capital of france?");
  await settle(120);

  const polite = dom.find((n) => n.getAttribute("aria-live") === "polite");
  assert.ok(polite, "no polite live region");
  assert.match(polite.textContent, /Paris/, "the answer itself must reach the live region");
  app?.dispose();
});

test("New chat stops the run that is still streaming", async () => {
  // It cleared the screen and left the turn running, so the next token
  // reconciled against an empty render and re-inserted the OLD conversation's
  // rows into what the user believed was a fresh chat, where it finished. Any
  // queued prompts ran into it too.
  const { dom, http, platform } = harness();
  // A body that never completes, so a run is genuinely live when New chat is
  // pressed. A finished turn has nothing to cancel and the test would pass
  // against the defect.
  http.on("/chat", () => ({
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        const enc = new TextEncoder();
        controller.enqueue(enc.encode(sse([["start", { msg_id: "m1", run_id: "r1" }]])));
        controller.enqueue(enc.encode(sse([["delta", { msg_id: "m1", text: "first answer" }]])));
        // deliberately never closed
      },
    }),
  }));
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "one");
  await settle();

  const newChat = dom.find((n) => n.dataset["action"] === "new-chat");
  assert.ok(newChat, "no New chat control");
  dom.click(newChat);
  await settle();

  const cancels = http.sent.filter((r) => r.url.includes("/cancel"));
  assert.ok(
    cancels.length > 0,
    `New chat must stop the live run, not just clear the screen. Sent: ${http.sent.map((r) => r.url).join(", ")}`,
  );
  app?.dispose();
});

test("New chat gives the new conversation its own id", async () => {
  // `setChat` was never called anywhere in the app, so every request from
  // every chat carried chat_id "unassigned". controller.ts says in as many
  // words that "an engine cannot tell two conversations apart if every turn
  // claims the same id" -- and against an engine keying server-side history by
  // chat_id, every conversation the user ever had was one thread.
  const { dom, http, platform } = harness();
  let n = 0;
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: `m${++n}`, run_id: `r${n}` }],
        ["delta", { msg_id: `m${n}`, text: "answer" }],
        ["end", { msg_id: `m${n}`, user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => `chat-${n}` });

  submit(dom, "one");
  await settle();
  dom.click(dom.find((d) => d.dataset["action"] === "new-chat") as never);
  await settle();
  submit(dom, "two");
  await settle();

  const chats = http.sent
    .filter((r) => r.url.includes("/chat"))
    .map((r) => JSON.parse(String(r.body ?? "{}")) as { chat_id?: string })
    .map((b) => b.chat_id);
  assert.equal(chats.length, 2, `expected two turns, got ${chats.length}`);
  assert.notEqual(chats[0], chats[1], `both turns claimed the same chat id: ${String(chats[0])}`);
});

test("a storage failure at boot shows the crash screen, not a dead-looking app", async () => {
  // `createApp` returns a typed BootResult for the failures it anticipated and
  // THROWS for a StoragePort failure -- reachable on the real platform via
  // SecurityError with site data blocked, or QuotaExceededError. The chrome is
  // already appended by then, so the throw skipped both the fatal screen and
  // the listener registrations: a perfectly rendered app, with a green Send
  // button, in which nothing ever happened again.
  const storage = createFakeStorage();
  storage.failNext("SecurityError: the operation is insecure");
  const { dom, platform } = harness({ storage });

  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  assert.equal(app, null, "a boot failure must not return a working app");
  assert.notEqual(dom.text(), "", "and must not leave a blank or silently dead page");
});

test("the conversation the user starts ON LAUNCH has a real chat id", async () => {
  // `chatId` defaults to the literal "unassigned", and `setChat` was only ever
  // called by the New chat handler -- so the first conversation of every
  // launch, on every device, went to the engine as "unassigned".
  // controller.ts says in as many words that "an engine cannot tell two
  // conversations apart if every turn claims the same id"; against an engine
  // keying server-side history by chat_id, every user's first chat was one
  // shared thread.
  //
  // The existing test asserted only that two chat ids DIFFER, and
  // "unassigned" !== "chat-2" passes that.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "answer" }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "chat-launch" });

  submit(dom, "the very first question");
  await settle();

  const body = JSON.parse(String(http.sent.find((r) => r.url.includes("/chat"))?.body ?? "{}")) as {
    chat_id?: string;
  };
  assert.notEqual(body.chat_id, "unassigned", "the first chat of a launch must have a real id");
  assert.equal(body.chat_id, "chat-launch");
  app?.dispose();
});

// ---- the chrome, driven ------------------------------------------------------
//
// `app/src/main.ts` measured 74% mutation survival -- the worst file in the
// package. The five tests above each pin one previously-reported defect and
// nothing around it. These cover the rest of what the chrome actually does.

const held = (frames: readonly (readonly [string, unknown])[]) => ({
  status: 200,
  headers: { "content-type": "text/event-stream" },
  body: new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sse(frames)));
      // deliberately never closed, so the turn stays live
    },
  }),
});

test("the Send button becomes Stop while a run is streaming", async () => {
  // `phase === "streaming" ? "stop" : "send"` -> `"send"` survived. The Stop
  // button never appears, so a run cannot be cancelled from the UI at all --
  // it keeps generating and keeps billing.
  const { dom, http, platform } = harness();
  http.on("/chat", () => held([["start", { msg_id: "m1", run_id: "r1" }], ["delta", { msg_id: "m1", text: "..." }]]));
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  const button = dom.find((n) => n.dataset["action"] === "send" || n.dataset["action"] === "stop");
  assert.ok(button, "no send control");
  assert.equal(button.dataset["action"], "send", "idle should offer Send");

  submit(dom, "hello");
  await settle();

  const live = dom.find((n) => n.dataset["action"] === "stop" || n.dataset["action"] === "send");
  assert.equal(live?.dataset["action"], "stop", "a streaming run must offer Stop");
  app?.dispose();
});

test("the keyboard height and BOTH insets reach the layout", async () => {
  // `keyboardHeightPx` -> 0 and `insets.top` -> `insets.bottom` both survived.
  // The composer never lifts above the keyboard (you type behind it), and the
  // top safe-area is read from the bottom, so content sits under the notch.
  const shell = createFakeShell(PHONE_INSETS);
  const dom = createFakeDom();
  const platform: Platform = {
    shell, storage: createFakeStorage(), secrets: createFakeSecrets(),
    http: createFakeHttp(), time: nodeTime(), kind: "web",
  };
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  shell.setKeyboardHeight(300);
  await settle(20);

  const screen = dom.find((n) => n.className === "screen");
  assert.ok(screen, "no screen element");
  const props = (screen as unknown as { style: { props: Record<string, string> } }).style.props;
  assert.equal(props["--keyboard-height"], "300px", "the keyboard height must reach the layout");
  // The four insets go on ROOT, not on the chat screen: settings and chats are
  // siblings of it, so an inset written on `screen` never reaches them -- which
  // is what left their headings under the status bar.
  const rootProps = (dom.root as unknown as { style: { props: Record<string, string> } }).style.props;
  assert.equal(rootProps["--inset-top"], `${PHONE_INSETS.top}px`, "the TOP inset must come from the top");
  assert.notEqual(
    rootProps["--inset-top"],
    `${PHONE_INSETS.bottom}px`,
    "reading the top inset from the bottom puts content under the notch",
  );
  assert.equal(rootProps["--inset-bottom"], `${PHONE_INSETS.bottom}px`, "and the bottom from the bottom");
  assert.equal(rootProps["--inset-left"], `${PHONE_INSETS.left}px`);
  assert.equal(rootProps["--inset-right"], `${PHONE_INSETS.right}px`);
  app?.dispose();
});

test("the layout keeps reacting after mount, not only on the first frame", async () => {
  // Dropping the onInsetsChanged / onKeyboardHeightChanged subscriptions
  // survived: the first frame is right and nothing after it is. Rotating the
  // phone or raising the keyboard changes nothing.
  const shell = createFakeShell(PHONE_INSETS);
  const dom = createFakeDom();
  const platform: Platform = {
    shell, storage: createFakeStorage(), secrets: createFakeSecrets(),
    http: createFakeHttp(), time: nodeTime(), kind: "web",
  };
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  const props = (dom.root as unknown as { style: { props: Record<string, string> } }).style.props;

  shell.setInsets({ top: 99, bottom: 12, left: 3, right: 4 });
  await settle(20);
  assert.equal(props["--inset-top"], "99px", "a rotation must reach the layout");
  assert.equal(props["--inset-bottom"], "12px", "and every other edge with it");
  app?.dispose();
});

test("a multi-delta answer paints ONE text row, not one per publish", async () => {
  // `render = diff.next` removed survived: the render state never advances, so
  // every publish re-inserts every row. A three-delta answer renders as three
  // separate paragraphs of the same growing text.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "one " }],
        ["delta", { msg_id: "m1", text: "two " }],
        ["delta", { msg_id: "m1", text: "three" }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "count");
  await settle(120);

  const textRows = dom.all().filter((n) => n.className.includes("row-text"));
  assert.equal(textRows.length, 1, `one answer must be one row, got ${textRows.length}`);
  assert.match(textRows[0]?.textContent ?? "", /one two three/);
  app?.dispose();
});

test("New chat clears the previous conversation off the screen", async () => {
  // `transcript.textContent = ""` removed survived.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "the first answer" }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "one");
  await settle(120);
  assert.match(dom.text(), /the first answer/);

  dom.click(dom.find((n) => n.dataset["action"] === "new-chat") as never);
  await settle();

  const transcript = dom.find((n) => n.className.includes("transcript"));
  assert.equal(transcript?.children.length, 0, "New chat must clear the transcript");
  assert.equal(
    /the first answer/.test(dom.text()),
    false,
    "and the live regions, which still held the previous conversation's answer in the "
      + "accessibility tree of what the user believes is an empty chat",
  );
  app?.dispose();
});

test("an empty or whitespace-only composer sends nothing", async () => {
  // `input.value.trim()` -> `input.value`, and the `text === ""` guard
  // neutered, both survived: whitespace starts a real turn against the engine.
  const { dom, http, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "");
  await settle();
  submit(dom, "   \n  ");
  await settle();

  assert.deepEqual(
    http.sent.filter((r) => r.url.includes("/chat")).map((r) => r.url),
    [],
    "nothing should have been sent",
  );
  app?.dispose();
});

test("a boot failure names what failed, alone on the screen, as an alert", async () => {
  // Four independent survivors in the fatal screen: no `textContent = ""` (so
  // it appends under the corpse of the UI), `role="alert"` -> `"status"` (so a
  // screen reader does not interrupt), and the detail replaced by a generic
  // message (so it no longer says WHAT failed).
  const storage = createFakeStorage();
  storage.failNext("SecurityError: the operation is insecure");
  const { dom, platform } = harness({ storage });

  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.equal(app, null);

  const alert = dom.find((n) => n.getAttribute("role") === "alert");
  assert.ok(alert, "the fatal screen must be an alert, or a screen reader never announces it");
  assert.match(dom.text(), /SecurityError/, "it must name what actually failed");
  assert.equal(
    dom.find((n) => n.dataset["action"] === "send"),
    null,
    "the dead chrome must be gone, not merely covered",
  );
});

test("the composer is emptied after a send, so a second tap is a second question", async () => {
  // Deleting `input.value = ""` survived. The text stays in the box, and the
  // next Send tap re-submits the SAME question -- the user double-sends and
  // pays twice, with no way to tell from the screen that it happened.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "answer" }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "the only question");
  await settle(120);

  const box = dom.find((n) => n.tagName === "TEXTAREA");
  assert.equal(box?.value, "", "the sent text must not still be in the composer");

  // And the guard that follows from it: submitting again now sends nothing.
  dom.find((n) => n.tagName === "FORM")?.dispatch("submit", { preventDefault: () => {} });
  await settle();
  assert.equal(
    http.sent.filter((r) => r.url.includes("/chat")).length,
    1,
    "a second tap on an empty composer must not re-send the last question",
  );
  app?.dispose();
});

test("no chat id the app sends is ever the placeholder", async () => {
  // `setChat(mintChatId())` -> `setChat("unassigned")` survived, because the
  // existing test only asserts two ids DIFFER and the launch id is real. The
  // placeholder is what `controller.ts` uses to mean "nobody has said which
  // conversation this is"; shipping it to an engine that keys history by
  // chat_id merges conversations.
  const { dom, http, platform } = harness();
  let n = 0;
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: `m${++n}`, run_id: `r${n}` }],
        ["delta", { msg_id: `m${n}`, text: "answer" }],
        ["end", { msg_id: `m${n}`, user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => `chat-${n}` });

  submit(dom, "one");
  await settle();
  dom.click(dom.find((d) => d.dataset["action"] === "new-chat") as never);
  await settle();
  submit(dom, "two");
  await settle();
  dom.click(dom.find((d) => d.dataset["action"] === "new-chat") as never);
  await settle();
  submit(dom, "three");
  await settle();

  const ids = http.sent
    .filter((r) => r.url.includes("/chat"))
    .map((r) => (JSON.parse(String(r.body ?? "{}")) as { chat_id?: string }).chat_id);

  assert.equal(ids.length, 3, `expected three turns, got ${ids.length}`);
  assert.equal(ids.includes("unassigned"), false, `a turn was sent as the placeholder: ${ids.join(", ")}`);
  assert.equal(new Set(ids).size, 3, `three conversations must have three ids: ${ids.join(", ")}`);
  app?.dispose();
});

test("the Send button's LABEL and its action agree", async () => {
  // Transposing `? actionStop : actionSend` survived, because the line below
  // sets `dataset.action` and is untouched: the button reads "Send" while the
  // turn streams, and tapping it stops the run. Label and behaviour disagree,
  // and nothing in the suite read the label.
  const { dom, http, platform } = harness();
  http.on("/chat", () => held([["start", { msg_id: "m1", run_id: "r1" }], ["delta", { msg_id: "m1", text: "..." }]]));
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  const button = () => dom.find((n) => n.dataset["action"] === "send" || n.dataset["action"] === "stop");
  assert.equal(button()?.textContent, en.actionSend, "idle must READ Send");

  submit(dom, "hello");
  await settle();

  const live = button();
  assert.equal(live?.dataset["action"], "stop");
  assert.equal(live?.textContent, en.actionStop, "a streaming turn must READ Stop, not just behave as Stop");
  app?.dispose();
});

test("an approval row shows the decision after the user answers it", async () => {
  // `buildTranscript(view.turn, view.approvals)` -> dropping the second
  // argument survived. The approval TABLE is where the decision lifecycle
  // lives; without it the row is built from the turn alone and stays `pending`
  // forever, so the user taps Deny and the card never acknowledges it.
  const { dom, http, platform } = harness();
  http.on("/approve/a1", () => ({ status: 200, headers: {}, body: streamOf(JSON.stringify({ ok: true })) }));
  http.on("/chat", () =>
    held([
      ["start", { msg_id: "m1", run_id: "r1" }],
      ["tool_call", { msg_id: "m1", call_id: "c1", name: "rm", args: { path: "/" } }],
      ["approval_request", { msg_id: "m1", approval_id: "a1", call_id: "c1", name: "rm", args: { path: "/" } }],
    ]),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "do it");
  await settle(120);

  const row = () => dom.find((n) => n.className.includes("row-approval"));
  assert.ok(row(), "the approval row should be on screen");
  assert.equal(row()?.dataset["state"], "pending");

  const deny = dom.find((n) => n.dataset["choice"] === "deny");
  assert.ok(deny, "no Deny button");
  dom.click(deny);
  await settle(120);

  assert.notEqual(
    row()?.dataset["state"],
    "pending",
    "the row must acknowledge the decision, not stay pending forever",
  );
  app?.dispose();
});

// ---- the accessibility wiring, which nothing had asserted -------------------
//
// A mutation audit found that `polite`'s aria-live was pinned and `assertive`'s
// was not, that the transcript's NOT being a live region -- the catastrophe its
// own comment describes -- was undefended, and that the composer's label could
// go back to the regression the code comment records as fixed.

test("the two live regions have the politeness each one is for", async () => {
  // `assertive.setAttribute("aria-live", "assertive")` was removable, and
  // could also be flipped to "polite". The assertive region carries approval
  // prompts and errors: an approval BLOCKS the run, so waiting politely for
  // the queue to drain is waiting for something that will not happen until
  // the user answers. Only `polite`'s attribute had a test.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  const regions = dom.all().filter((n) => n.getAttribute("aria-live") !== null);
  assert.deepEqual(
    regions.map((n) => n.getAttribute("aria-live")).sort(),
    ["assertive", "polite"],
    "exactly one polite region and one assertive one",
  );
  for (const region of regions) {
    assert.ok(region.className.includes("sr-only"), "a live region is not visible");
  }
  app?.dispose();
});

test("the transcript is NOT a live region", async () => {
  // Nothing asserted this, and the consequence is written out in main.ts: the
  // transcript is mutated on every publish, so aria-live here makes the reader
  // restart on each token batch and no sentence is ever finished. A one-line
  // addition away, and undetectable.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  const log = dom.find((n) => n.getAttribute("role") === "log");
  assert.ok(log, "the transcript is a log");
  assert.equal(log.getAttribute("aria-live"), null, "and must never also be a live region");
  assert.equal(log.getAttribute("aria-label"), en.appName, "it must still be named");
  app?.dispose();
});

test("the message field is labelled as the field, not as the button beside it", async () => {
  // `input.setAttribute("aria-label", strings.composerLabel)` was removable
  // and could be given the Send button's name -- which is the exact regression
  // the line's own comment records: the composer announced as "Send, edit
  // text".
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  const box = dom.find((n) => n.tagName === "TEXTAREA");
  assert.ok(box);
  assert.equal(box.getAttribute("aria-label"), en.composerLabel);
  assert.notEqual(box.getAttribute("aria-label"), en.actionSend, "not the button's name");
  app?.dispose();
});

// ---- an unreachable engine must not be a dead app ---------------------------

test("the app STARTS when the engine is not answering, and says so", async () => {
  // PR #4647 made the health probe a hard boot gate, and the whole app
  // rendered "PraisonAI could not start: 404" -- 17 end-to-end tests went red
  // on main, and on a phone with no desktop engine to reach the app simply
  // would not open. The user cannot fix it either: the address is changed in
  // Settings, and Settings is behind the app that will not start.
  const { dom, platform } = harness(); // no /health route: the engine is unreachable
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  assert.notEqual(app, null, "an unreachable engine must not stop the app from starting");
  assert.ok(dom.find((n) => n.tagName === "TEXTAREA"), "the composer must be there");
  assert.ok(dom.find((n) => String(n.dataset["action"]) === "send"), "and the send control");

  const notice = dom.find((n) => n.className.includes("row-notice"));
  assert.ok(notice, `the app must SAY the engine is not answering:\n${dom.text()}`);
  assert.equal(notice.dataset["tone"], "warning");

  // Assertive, because the user is about to type into something that cannot
  // reply yet -- waiting politely for the queue means they find out by sending.
  const shouted = dom.all().find((n) => n.getAttribute("aria-live") === "assertive");
  assert.match(String(shouted?.textContent), /not answering yet/);
  app?.dispose();
});

test("a HEALTHY engine boots with no warning -- the pair", async () => {
  // Without this, an app that always warned would pass the test above and cry
  // wolf on every launch.
  const { dom, http, platform } = harness();
  http.on("/health", () => ({
    status: 200,
    headers: {},
    body: streamOf(JSON.stringify({ ok: true, version: PROTOCOL_VERSION })),
  }));
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  assert.notEqual(app, null);
  assert.equal(
    dom.find((n) => n.className.includes("row-notice")),
    null,
    "a healthy engine must not be reported as unhealthy",
  );
  app?.dispose();
});

test("a PERMANENT refusal still stops the app, with a name", async () => {
  // The other half. A retryable unreadiness boots and warns; a protocol
  // mismatch never resolves itself, so booting into it only defers the same
  // failure to the user's first message. It must still be fatal.
  //
  // Version 1, not 99: a NEWER engine is deliberately accepted, because
  // version.ts treats unknown fields as additive and refusing one would strand
  // every shipped client on the day the engine ships first. Too OLD is the
  // permanent refusal.
  const { dom, http, platform } = harness();
  http.on("/health", () => ({
    status: 200,
    headers: {},
    body: streamOf(JSON.stringify({ ok: true, version: 1 })),
  }));
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  assert.equal(app, null, "a version mismatch must refuse to boot");
  assert.match(dom.text(), /could not start/, dom.text());
  assert.match(dom.text(), /too_old|engine=1|protocol/, "and it must name the reason");
});

// ---- the modules the barrel used to gate (issue #4635) ----------------------
//
// Nine view models had 128 tests and zero non-test importers: settings, the
// chat list, follow-the-stream, locale/direction and the composer were all
// maintained, tested and unreachable from `main.ts`. These drive the real
// `mount()` and assert each is now wired.

test("tapping Settings paints the settings screen", async () => {
  // The acceptance test named in the issue. `router.subscribe` had no non-test
  // caller, so pushing the settings route rendered nothing: the tap painted a
  // blank and the next back gesture was consumed instead of exiting.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();

  assert.ok(
    dom.find((n) => n.className.includes("screen-settings")),
    `Settings painted nothing:\n${dom.text()}`,
  );
  // And the chat screen is hidden, not left underneath.
  const chat = dom.find((n) => n.className === "screen");
  assert.equal(chat?.hidden, true, "the chat screen must be hidden while settings shows");
  app?.dispose();
});

test("the settings screen is EDITABLE, so a phone can point the engine somewhere reachable", async () => {
  // The recovery the remote-http default depends on. A phone reaches no
  // `127.0.0.1:8765`, so first launch warns that the engine is not answering --
  // and the only fix is to change `baseUrl`. That was impossible: every setting
  // rendered as a read-only <span>, and `facade.set` / `validateInput` had no
  // caller, so an unreachable engine had no way back. The row is a real field
  // now; committing it must PERSIST -- createApp loads settings first and builds
  // the engine from them, so the change takes effect on the next launch, which
  // is the recovery this unblocks.
  const storage = createFakeStorage();
  const { dom, platform } = harness({ storage });
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();

  // The baseUrl row must carry an editable control, not a read-only span.
  const field = dom.find(
    (n) =>
      (n.tagName === "INPUT" || n.tagName === "SELECT") &&
      n.getAttribute("aria-label") === "Engine address",
  );
  assert.ok(field, `the engine address must be editable:\n${dom.text()}`);

  (field as { value: string }).value = "http://10.0.0.7:9000";
  dom.change(field as never);
  await settle();

  // Persisted in the live facade AND written through to storage, so the next
  // launch's `settings.load()` reads the address the user set, not the default.
  assert.equal(app?.settings.get("baseUrl"), "http://10.0.0.7:9000", "the edit must persist in the facade");
  const raw = await storage.read({ namespace: "settings", id: "app" });
  assert.ok(
    raw !== null && raw.includes("10.0.0.7:9000"),
    `the edit must survive a relaunch:\n${String(raw)}`,
  );
  app?.dispose();
});

test("a setting the store REFUSES resets the field instead of showing a phantom value", async () => {
  // `set` returns false for a value the def rejects, and `validateInput`
  // returns null for one that will not parse. Either way the field must fall
  // back to what is actually stored -- a screen showing a value the store never
  // accepted is a setting the user believes they changed and did not.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();

  // The engine choice is a closed set (`choices: [remote-http]`), so an unknown
  // id must be refused and the select must snap back.
  const select = dom.find(
    (n) => n.tagName === "SELECT" && n.getAttribute("aria-label") === "Engine",
  );
  assert.ok(select, "the engine choice must be a select");
  (select as { value: string }).value = "not-a-real-engine";
  dom.change(select as never);
  await settle();

  assert.equal(app?.settings.get("engineId"), ENGINE_REMOTE_HTTP, "a rejected choice must not persist");
  assert.equal((select as { value: string }).value, ENGINE_REMOTE_HTTP, "the field must reset to what is stored");
  app?.dispose();
});

test("a storage failure while editing a setting stays LOCAL, not fatal", async () => {
  // `commit` was a fire-and-forget `void commit(...)`, and `settings.set`
  // persists through StoragePort -- which rejects on a real device
  // (SecurityError with site data blocked, QuotaExceededError). Left to float,
  // that rejection reached the global crash handler and replaced the WHOLE app
  // with the fatal screen; worse, the store had already committed the value to
  // memory before persisting, so the field showed an address the next launch
  // would never read. A failed write must stay local: the app keeps working and
  // the field resets to what is actually stored.
  const storage = createFakeStorage();
  const { dom, platform } = harness({ storage });
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);

  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();

  const field = dom.find(
    (n) =>
      (n.tagName === "INPUT" || n.tagName === "SELECT") &&
      n.getAttribute("aria-label") === "Engine address",
  );
  assert.ok(field, `the engine address must be editable:\n${dom.text()}`);

  const before = app?.settings.get("baseUrl");
  storage.failNext("QuotaExceededError: the storage is full");
  (field as { value: string }).value = "http://10.0.0.7:9000";
  dom.change(field as never);
  await settle();

  // The app must survive: the chat screen and composer are still reachable, and
  // nothing escalated to the fatal "could not start" screen.
  assert.ok(
    dom.find((n) => n.tagName === "TEXTAREA" || n.tagName === "INPUT" || n.tagName === "SELECT"),
    `a failed setting write must not take down the app:\n${dom.text()}`,
  );
  assert.equal(
    /could not start/.test(dom.text()),
    false,
    "a failed settings write must not become the app-wide crash screen",
  );

  // The store rolled the value back, so the field shows what is actually
  // stored -- not a phantom the next launch will not read.
  assert.equal(app?.settings.get("baseUrl"), before, "a value that did not persist must not linger in memory");
  assert.equal((field as { value: string }).value, String(before), "the field must reset to what is stored");
  app?.dispose();
});

test("a route change MOVES focus to the new heading, and Back restores it", async () => {
  // focus.ts computes where focus belongs on every route change and the app
  // used to throw the answer away -- it read the target only to decide whether
  // to announce, always as a "push", and never called `focus()`. So a
  // keyboard or screen-reader user who opened Settings was left focused on the
  // button they tapped (now on a hidden screen) or dropped to <body>, and Back
  // never returned them to where they were.
  // The fake shell is built directly, so `pressBack()` (a test-only driver, not
  // part of ShellPort) is reachable to drive the OS back gesture.
  const shell = createFakeShell(PHONE_INSETS);
  const dom = createFakeDom();
  const platform: Platform = {
    shell, storage: createFakeStorage(), secrets: createFakeSecrets(),
    http: createFakeHttp(), time: nodeTime(), kind: "web",
  };
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);

  const toSettings = dom.find((n) => n.dataset["route"] === "settings");
  assert.ok(toSettings, "no settings button");
  dom.click(toSettings as never);
  await settle();

  // Focus is on the settings screen's heading, not on the hidden chat screen.
  const focused = dom.activeElement();
  assert.equal(
    focused?.dataset["focusId"],
    "heading:settings",
    `a route change must move focus to the new heading, landed on: ${
      focused?.dataset["focusId"] ?? "<nothing>"
    }`,
  );

  // Back pops the route -- and restores focus to the control that opened it,
  // so the user lands where they were rather than at the top of the chat.
  shell.pressBack();
  await settle();
  assert.equal(
    dom.activeElement(),
    toSettings,
    "Back must restore focus to the control that opened the screen",
  );
  app?.dispose();
});

test("opening Settings tells the shell there is a route to come back to", async () => {
  // The whole point, end to end, on the path the user walks. On a device the
  // app's ANSWER to the back press was measured arriving 5.4 s after it -- long
  // past the 400 ms the native side waits -- so Android acted on the press
  // itself and the app left the screen the user was on. What stops that is the
  // declaration made when the route is PUSHED, before any press exists.
  const shell = createFakeShell(PHONE_INSETS);
  const dom = createFakeDom();
  const platform: Platform = {
    shell, storage: createFakeStorage(), secrets: createFakeSecrets(),
    http: createFakeHttp(), time: nodeTime(), kind: "web",
  };
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);
  assert.equal(shell.canGoBack(), false, "the chat the app opens on is the root");

  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();
  assert.equal(shell.canGoBack(), true, "Settings must be declared as a route back");

  shell.pressBack();
  await settle();
  assert.equal(shell.canGoBack(), false, "and popped back to the root");
  assert.equal(shell.pressBack(), false, "the root still lets the OS act");
  app?.dispose();
});

test("the crash screen stops claiming there is a route to go back to", async () => {
  // The fatal screen has no routes. If the last thing declared was `true`, the
  // native side keeps waiting on a webview that will never answer again, and
  // back on a dead app does nothing at all -- the one outcome that is worse
  // than exiting.
  const shell = createFakeShell(PHONE_INSETS);
  const dom = createFakeDom();
  const platform: Platform = {
    shell, storage: createFakeStorage(), secrets: createFakeSecrets(),
    http: createFakeHttp(), time: nodeTime(), kind: "web",
  };
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);
  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();
  assert.equal(shell.canGoBack(), true);

  // A real crash, through the real handler: an uncaught error at the window.
  dom.view.dispatch("error", { error: new Error("the webview fell over") });
  await settle();
  assert.match(dom.text(), /Something went wrong/, "the crash screen did not paint");
  assert.equal(shell.canGoBack(), false, "a crashed app must not swallow the back gesture");
  app?.dispose();
});

test("the chat list is painted from the session, and a chat reopens", async () => {
  // `session.list()` had no app caller and the chat list no way to be reached,
  // so a conversation, once left, could never be reopened. The chats route must
  // render the stored chats -- from the SESSION, the thing that had no reader --
  // and tapping one must reopen it.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);

  // Store a conversation through the session directly. Persistence on a real
  // turn is the in-process engine's job; the remote harness never records, so
  // seed the session the list reads from. This is the object `list()` returns.
  await app!.session.record("what is the capital of France", "Paris");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();

  const list = dom.find((n) => n.className.includes("screen-chats"));
  assert.ok(list, `the chat list painted nothing:\n${dom.text()}`);
  const row = dom.find((n) => n.dataset["action"] === "open-chat");
  assert.ok(row, `a stored conversation must be an openable row:\n${dom.text()}`);

  // And opening it returns to the chat screen carrying that conversation.
  dom.click(row as never);
  await settle();
  const chat = dom.find((n) => n.className === "screen");
  assert.equal(chat?.hidden, false, "opening a chat must show the chat screen");
  assert.match(dom.text(), /Paris/, "the reopened conversation must be painted");
  app?.dispose();
});

test("a turn sent AFTER reopening a chat lands below the history, not above it", async () => {
  // The reopened messages were appended as untracked <p> nodes while `render`
  // was reset to empty, so the next turn reconciled from nothing and
  // `applyOps` inserted its rows at index 0 -- ABOVE the restored history. The
  // newest answer rendered above the older conversation, and the history sat
  // outside `render` where no later reconcile could touch it. Painting the
  // history THROUGH the reconciler keeps both turns in one coordinate system.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "the newest answer" }],
        ["end", { msg_id: "m1", user_index: 2, assistant_index: 3, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);

  await app!.session.record("what is the capital of France", "Paris");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "open-chat") as never);
  await settle();

  submit(dom, "and its population?");
  await settle(120);

  const transcript = dom.find((n) => n.className.includes("transcript"));
  assert.ok(transcript, "no transcript");
  const text = (transcript.children as { textContent: string }[]).map((c) => c.textContent).join(" | ");

  // The restored history must survive the next turn -- it must not be wiped by
  // a reconcile that never knew it existed.
  assert.match(text, /capital of France/, `the user's original question was lost:\n${text}`);
  assert.match(text, /Paris/, `the reopened answer was lost:\n${text}`);
  assert.match(text, /the newest answer/, `the new turn did not render:\n${text}`);

  // And order: the newest answer is LAST, below the history it followed.
  const question = text.indexOf("capital of France");
  const answer = text.indexOf("Paris");
  const newest = text.indexOf("the newest answer");
  assert.ok(
    question < newest && answer < newest,
    `the newest turn must render below the history, got order:\n${text}`,
  );
  app?.dispose();
});

test("opening another chat mid-run keeps that run's answer OUT of it", async () => {
  // The cross-chat leak (greptile P1). New chat and deleting the open chat both
  // stop the run in flight before reseeding the screen; Open chat did not. So a
  // run still streaming in the conversation you LEFT kept going, and its
  // terminal publish -- which the controller always emits, even on abort --
  // reconciled the old chat's answer into the transcript just seeded with the
  // chat you OPENED, where it was then promoted into history and reopened there.
  //
  // Two defences, both asserted here: Open chat now stops the previous run, and
  // the app drops any publish arriving for a chat that has issued no turn of its
  // own -- so even the guaranteed terminal frame paints nothing into the wrong
  // conversation.
  const { dom, http, platform } = harness();

  // Chat A's run stays open: `start` and a `delta`, then the stream hangs until
  // the test releases it -- exactly the shape of a reply still in flight.
  //
  // Released through a NAMED ACCESSOR rather than by calling `release?.()`, for
  // two reasons that turn out to be the same reason.
  //
  // The compiler's: `release` is assigned only inside the stream's `start`
  // callback, and TypeScript's control-flow analysis does not follow
  // assignments made inside a callback. At the call site below it is therefore
  // still narrowed to the `null` it was initialised with, `?.` short-circuits,
  // and the call target is `never` -- TS2349, "Type 'never' has no call
  // signatures".
  //
  // The test's: that narrowing is right about the risk. `release?.()` on a null
  // releaser silently does NOTHING. Chat A's run would never terminate, no
  // terminal publish would ever be emitted, and every assertion below -- all of
  // which say chat B is free of chat A's rows -- would pass for the wrong
  // reason, proving only that a leak that never happened did not happen. An
  // optional call is the wrong tool for a value the test depends on. This one
  // fails loudly instead.
  let release: (() => void) | null = null;
  const releaseChatA = (): void => {
    assert.ok(release !== null, "chat A's stream never opened, so there was nothing to release");
    release();
  };
  http.on("/chat", () => ({
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        const enc = new TextEncoder();
        controller.enqueue(enc.encode(sse([["start", { msg_id: "mA", run_id: "rA" }]])));
        controller.enqueue(enc.encode(sse([["delta", { msg_id: "mA", text: "LEAKED-ANSWER-A" }]])));
        release = () => {
          controller.enqueue(
            enc.encode(
              sse([["end", { msg_id: "mA", user_index: 0, assistant_index: 1, versions: 1, active: 0 }]]),
            ),
          );
          controller.close();
        };
      },
    }),
  }));

  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);

  // A second, stored conversation to open into. Recorded through the session so
  // the chat list has a real row to tap.
  await app!.session.record("chat B question", "chat B answer");

  // Start chat A's run and let it stream the delta, but NOT the end.
  submit(dom, "chat A question");
  await settle(80);
  assert.match(transcriptRows(dom).join("\n"), /LEAKED-ANSWER-A/, "chat A never started streaming");

  // Open chat B WHILE chat A is still in flight.
  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "open-chat") as never);
  await settle();

  // Now let chat A's run finish. Its terminal publish must not reach chat B.
  releaseChatA();
  await settle(120);

  // Chat B shows its OWN stored conversation and nothing else. With the leak
  // present, chat A's terminated run publishes into B as a spurious error row
  // (its turn was cleared by `setChat`, so its `end` lands on an idle turn and
  // `finish` synthesises "the engine produced no output") plus a "before_start"
  // dropped row -- both belonging to a run that was never chat B's.
  const rows = transcriptRows(dom);
  const joined = rows.join("\n");
  assert.match(joined, /chat B question/, `chat B's own history was lost:\n${joined}`);
  assert.match(joined, /chat B answer/, `chat B's own answer was lost:\n${joined}`);
  assert.equal(
    rows.some((r) => r.startsWith("row row-error") || r.startsWith("row row-dropped")),
    false,
    `the previous chat's terminated run leaked a row into the opened conversation:\n${joined}`,
  );
  assert.equal(
    joined.includes("LEAKED-ANSWER-A") || joined.includes("chat A question"),
    false,
    `the previous chat's message leaked into the opened conversation:\n${joined}`,
  );
  // Exactly chat B's two rows -- nothing appended below them.
  assert.equal(rows.length, 2, `chat B must show only its own turn:\n${joined}`);
  app?.dispose();
});

test("a storage failure while the chat list loads stays LOCAL, not fatal", async () => {
  // The list load was a floating `void (async ...)()` with no rejection
  // handler. A StoragePort rejection -- SecurityError, QuotaExceeded -- reached
  // the global crash handler and replaced the WHOLE app with the fatal screen,
  // instead of showing a local error the user can back out of.
  const { dom, storage, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null, "the app must boot before the list is even asked for");

  storage.failNext("SecurityError: the operation is insecure");
  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();

  // The chat screen and its composer must still be reachable: this was a local
  // failure, not a boot failure.
  assert.ok(dom.find((n) => n.tagName === "TEXTAREA"), `the app must survive a list failure:\n${dom.text()}`);
  // And nothing must have escalated to the fatal "could not start" screen.
  assert.equal(
    /could not start/.test(dom.text()),
    false,
    "a failed chat list must not become the app-wide crash screen",
  );
  app?.dispose();
});

test("the composer field mirrors the composer view model", async () => {
  // The raw <textarea> is backed by composer.ts now: typing updates the draft
  // and enables Send, an empty field disables it. Draft persistence, the
  // Enter policy and autosize all live in that one state.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  const box = dom.find((n) => n.tagName === "TEXTAREA") as never;
  const send = () => dom.find((n) => n.dataset["action"] === "send") as never;
  assert.equal((send() as { disabled: boolean }).disabled, true, "Send is disabled on an empty draft");

  (box as { value: string }).value = "a question";
  (box as { dispatch(t: string, e: unknown): void }).dispatch("input", {});
  assert.equal((send() as { disabled: boolean }).disabled, false, "typing must enable Send");
  app?.dispose();
});

test("the locale and direction are detected, not hardcoded to en", async () => {
  // main.ts:173 passed `locale: "en"` as a literal, so every RTL user got an
  // LTR layout and the #4607 direction fix was unreachable. An Arabic device
  // must lay out right-to-left.
  const { dom, platform } = harness();
  const app = await mount({
    root: dom.root as never,
    platform,
    now: () => 1,
    newChatId: () => "c1",
    locales: ["ar-EG"],
  });

  assert.equal(dom.root.getAttribute("dir"), "rtl", "an Arabic locale must lay out RTL");
  app?.dispose();
});

test("an English device still lays out left-to-right -- the pair", async () => {
  const { dom, platform } = harness();
  const app = await mount({
    root: dom.root as never,
    platform,
    now: () => 1,
    newChatId: () => "c1",
    locales: ["en-GB"],
  });

  assert.equal(dom.root.getAttribute("dir"), "ltr");
  app?.dispose();
});

// ---- the recovery path, end to end -----------------------------------------
//
// A phone reaches no `127.0.0.1:8765`, so first launch warns that the engine
// is not answering and points at Settings. Everything from that warning to a
// working engine has to hold, and two links of it did not: a refused value
// vanished with no explanation, and a corrected address changed nothing until
// the app was force-quit and relaunched.

const settingField = (dom: ReturnType<typeof createFakeDom>, label: string) =>
  dom.find(
    (n) => (n.tagName === "INPUT" || n.tagName === "SELECT") && n.getAttribute("aria-label") === label,
  );

const openSettings = async (dom: ReturnType<typeof createFakeDom>): Promise<void> => {
  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();
};

test("a corrected engine address redirects the very NEXT message, with no relaunch", async () => {
  // The whole point of making the screen editable. `enginesFor` read `baseUrl`
  // once at construction and the app builds its engine once at boot, so the
  // address the user typed was persisted, displayed, and then ignored for the
  // rest of the session -- every message still went to the unreachable default.
  const { dom, http, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);

  await openSettings(dom);
  const field = settingField(dom, "Engine address");
  assert.ok(field, `the engine address must be editable:\n${dom.text()}`);
  field.value = "http://10.0.0.7:9000";
  dom.change(field as never);
  await settle();

  submit(dom, "hello");
  await settle();

  const chats = http.sent.filter((r) => r.url.endsWith("/chat")).map((r) => r.url);
  assert.ok(chats.length > 0, "the message never reached the transport at all");
  assert.equal(
    chats.at(-1),
    "http://10.0.0.7:9000/chat",
    `the turn still went to the old address: ${chats.join(", ")}`,
  );
  app?.dispose();
});

test("a REFUSED setting says so on screen, instead of the field quietly snapping back", async () => {
  // A field that resets and says nothing is indistinguishable from a mis-tap,
  // a lost keystroke, or a save that worked. On the one screen whose job is to
  // repair an unreachable engine, "nothing happened and nothing was said" is
  // the failure mode that leaves a user re-typing the same rejected value.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  await openSettings(dom);
  const select = settingField(dom, "Engine");
  assert.ok(select, "the engine choice must be a select");
  select.value = "not-a-real-engine";
  dom.change(select as never);
  await settle();

  // Still refused, and still snapped back -- the existing guarantees.
  assert.equal(app?.settings.get("engineId"), ENGINE_REMOTE_HTTP, "a rejected choice must not persist");
  assert.equal(select.value, ENGINE_REMOTE_HTTP, "the field must reset to what is stored");

  // And now SAID. Visibly, for a sighted user...
  const shown = dom.find((n) => n.className.includes("setting-error") && n.hidden === false);
  assert.ok(shown, `a refused setting was dropped silently:\n${dom.text()}`);
  assert.match(shown.textContent, /Engine/, "the message must name the setting it refused");

  // ...and out loud, because the field it belongs to may be off screen and a
  // screen-reader user gets no "it snapped back" cue at all.
  const spoken = dom.find((n) => n.getAttribute("aria-live") === "assertive");
  assert.match(spoken?.textContent ?? "", /Engine/, "a refused setting must also be announced");
  app?.dispose();
});

test("an ACCEPTED setting clears its OWN refusal, and only its own", async () => {
  // Two pairs in one, because each guards the other's cheap implementation. A
  // screen that reports every write as refused would satisfy the test above
  // while making the setting look permanently broken, so an accepted write has
  // to clear its message. And clearing ALL of them on any accepted write would
  // wipe a refusal the user has not read off a DIFFERENT setting -- the note
  // beside `engineId` is still true while `baseUrl` is being edited.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  const errorFor = (key: string) =>
    dom.find((n) => n.dataset["settingError"] === key && n.hidden === false);

  await openSettings(dom);
  const select = settingField(dom, "Engine");
  assert.ok(select);
  select.value = "not-a-real-engine";
  dom.change(select as never);
  await settle();
  assert.ok(errorFor("engineId"), "the refusal this test clears must be on screen first");

  // An accepted write to a DIFFERENT setting leaves it alone.
  const field = settingField(dom, "Engine address");
  assert.ok(field);
  field.value = "http://10.0.0.7:9000";
  dom.change(field as never);
  await settle();
  assert.equal(app?.settings.get("baseUrl"), "http://10.0.0.7:9000", "the accepted edit must persist");
  assert.equal(errorFor("baseUrl"), null, "an accepted write must not accuse itself");
  assert.ok(errorFor("engineId"), "a refusal must not be cleared by a write to another setting");

  // An accepted write to the SAME setting does clear it.
  select.value = ENGINE_REMOTE_HTTP;
  dom.change(select as never);
  await settle();
  assert.equal(app?.settings.get("engineId"), ENGINE_REMOTE_HTTP);
  assert.equal(
    errorFor("engineId"),
    null,
    `an accepted write must leave no refusal on its own field:\n${dom.text()}`,
  );
  app?.dispose();
});

test("on a device with nothing configured, the first message reaches the in-process Agent", async () => {
  // The whole wiring, end to end, from the real composition root: platform
  // kind "tauri", empty storage, no engine picked -- so `defaultEngineIdFor`
  // decides -- and a message typed into the real composer. It must arrive at
  // praisonai's `Agent`, and the answer must come back through the real
  // engine, controller and transcript onto the screen. No network and no
  // key: the Agent class is a scripted one handed in through the seam
  // `appEngines` exposes for it, the way praisonai-ts's own engine tests
  // script theirs. Every other piece is the shipping one.
  const prompts: string[] = [];
  const configs: { instructions: string; llm?: string }[] = [];
  class ScriptedAgent {
    lastStopReason: "completed" | null = "completed";
    constructor(config: { instructions: string; llm?: string }) {
      configs.push(config);
    }
    setHistory() {}
    async *streamEvents(prompt: string) {
      prompts.push(prompt);
      yield { type: "text", delta: "The capital of France is Paris." } as const;
      yield { type: "finish", text: "The capital of France is Paris." } as const;
    }
  }

  const { dom, http, platform: web } = harness();
  http.on("/chat", () => {
    throw new Error("the remote engine must not be contacted on a device");
  });
  const platform: Platform = { ...web, kind: "tauri" };
  const app = await mount({
    root: dom.root as never,
    platform,
    now: () => 1,
    newChatId: () => "c1",
    loadAgent: async () => ScriptedAgent,
  });
  assert.ok(app, "the app must mount");
  assert.equal(app.engine.id, ENGINE_PRAISONAI_TS, "with nothing configured, a device runs in-process");
  assert.equal(
    app.settings.get("engineId"),
    ENGINE_PRAISONAI_TS,
    "and Settings shows the same engine -- main.ts must hand boot the platform's defs, not the web's",
  );

  submit(dom, "capital of france?");
  await settle(120);

  assert.deepEqual(prompts, ["capital of france?"], "the typed message must reach the Agent verbatim");
  assert.equal(configs.length, 1, "one Agent, built on the first turn -- not at boot");
  assert.equal(configs[0]?.llm, "gpt-4o-mini", "with the model the settings default to");
  const answer = dom.find((n) => n.textContent.includes("Paris") && n.className.includes("row"));
  assert.ok(answer, "the Agent's answer must reach the transcript");
  assert.equal(dom.find((n) => n.className.includes("row-error")), null, "and nothing must fail on the way");
  await app.dispose();
});

// ---- deleting a conversation ------------------------------------------------
//
// `session.remove` -> `repository.remove` -> `storage.remove` were implemented,
// unit-tested and contract-tested; `intents.ts` decoded a `delete-chat` intent
// and had a test for it. Nothing in the app rendered a control carrying that
// intent and `perform` had no case for it, so a conversation, once started,
// could not be removed from the device by any sequence of taps. Storage grew
// forever and anything typed into a chat stayed there.

test("a conversation can be DELETED from the chat list", async () => {
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);
  await app!.session.record("what is the capital of France", "Paris");
  assert.equal((await app!.session.list()).length, 1, "precondition: one stored chat");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();

  const del = dom.find((n) => n.dataset["action"] === "delete-chat");
  assert.ok(del, `no delete control on a chat row:\n${dom.text()}`);
  // Two taps: the first arms, the second deletes.
  dom.click(del as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "delete-chat") as never);
  await settle();

  assert.deepEqual(await app!.session.list(), [], "the conversation is still on disk");
  app?.dispose();
});

test("the FIRST tap on Delete does not delete", async () => {
  // The pair. A single-tap irreversible delete a few millimetres from the row
  // that opens the chat is a conversation lost to a mis-tap, and there is no
  // undo anywhere in this app.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await app!.session.record("keep me", "sure");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "delete-chat") as never);
  await settle();

  assert.equal((await app!.session.list()).length, 1, "one tap must not delete");
  // And the control says so rather than looking unchanged.
  const del = dom.find((n) => n.dataset["action"] === "delete-chat");
  assert.equal(del?.dataset["armed"], "true", "the armed state must be visible");
  assert.equal(del?.textContent, en.actionConfirmDelete);
  app?.dispose();
});

test("deleting the chat that is OPEN clears it off the screen", async () => {
  // Otherwise the user is left typing into a transcript that no longer exists
  // on disk, and the next turn silently re-creates it.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await app!.session.record("what is the capital of France", "Paris");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "open-chat") as never);
  await settle();
  assert.match(dom.text(), /Paris/, "precondition: the chat is open");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "delete-chat") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "delete-chat") as never);
  await settle();

  const transcript = dom.find((n) => n.className.includes("transcript"));
  assert.doesNotMatch(
    transcript?.textContent ?? "",
    /Paris/,
    "the deleted conversation is still painted",
  );
  app?.dispose();
});

test("a delete that STORAGE refuses is said, not swallowed", async () => {
  // `storage.remove` rejects on a real device -- SecurityError with site data
  // blocked. A delete that quietly did nothing leaves the user believing a
  // conversation is gone when it is still there.
  const storage = createFakeStorage();
  const { dom, platform } = harness({ storage });
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await app!.session.record("keep me", "sure");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  const remove = storage.remove.bind(storage);
  (storage as { remove: (k: unknown) => Promise<void> }).remove = async () => {
    throw new Error("SecurityError");
  };
  dom.click(dom.find((n) => n.dataset["action"] === "delete-chat") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "delete-chat") as never);
  await settle();
  (storage as { remove: (k: unknown) => Promise<void> }).remove = remove as never;

  const assertive = dom.find((n) => n.getAttribute("aria-live") === "assertive");
  assert.match(assertive?.textContent ?? "", /could not be deleted/i, `said nothing:\n${dom.text()}`);
  assert.equal((await app!.session.list()).length, 1, "and nothing was actually removed");
  app?.dispose();
});

test("a delete label names ONLY the chat, not its time and button text", async () => {
  // `syncDeleteArming` re-derived the title from `parentElement.textContent`,
  // which folds in the chat title, the relative time and the button's own word
  // -- so arming turned "Delete Trip to Kyoto" into "Delete Trip to Kyoto3h
  // agoConfirm". The clean title is carried on the button's dataset instead.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await app!.session.record("what is the capital of France", "Paris");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();

  const del = dom.find((n) => n.dataset["action"] === "delete-chat");
  assert.ok(del, `no delete control on a chat row:\n${dom.text()}`);
  // The clean title -- exactly what `deleteChat(title)` names before arming.
  const title = (del.getAttribute("aria-label") ?? "").replace(/^Delete /, "");
  assert.equal(del.getAttribute("aria-label"), en.deleteChat(title), "the resting label is not the clean title");
  dom.click(del as never); // arm
  await settle();

  const armed = dom.find((n) => n.dataset["action"] === "delete-chat");
  const label = armed?.getAttribute("aria-label") ?? "";
  // The armed label is the confirm string built from the SAME clean title --
  // not the row's whole text (title + relative time + the button's own word),
  // which is what `parentElement.textContent` used to fold in.
  assert.equal(label, en.deleteChatConfirm(title), `the armed label was not the clean confirm string:\n${label}`);
  assert.doesNotMatch(label, /ago/, `the armed label folded in the row's time:\n${label}`);
  app?.dispose();
});

test("a delete when the chat list read REJECTS stays LOCAL, not fatal", async () => {
  // The title shown in the confirmation is looked up via `session.list()`,
  // which reads StoragePort and REJECTS on a real device. That read sits
  // outside the remove try and `perform` is invoked through a floating `void`,
  // so a rejection there reached the global crash handler and replaced the
  // WHOLE app with the fatal screen -- for a lookup that only decides a label.
  const storage = createFakeStorage();
  const { dom, platform } = harness({ storage });
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await app!.session.record("keep me", "sure");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();

  storage.failNext("SecurityError: site data blocked");
  dom.click(dom.find((n) => n.dataset["action"] === "delete-chat") as never);
  await settle();

  assert.equal(
    /could not start/.test(dom.text()),
    false,
    "a failed chat-list read must not become the app-wide crash screen",
  );
  assert.equal((await app!.session.list()).length, 1, "and nothing was removed");
  app?.dispose();
});

test("a chat row SHOWS when it was last used", async () => {
  // `buildChatList` has computed `updatedLabel` for every row since it was
  // written and the renderer dropped it on the floor, so a list SORTED by
  // recency displayed none of it -- and two chats both called "Untitled" were
  // indistinguishable. The label reaches the row's visible text AND its
  // accessible name, from one string, so the two cannot drift.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1_000_000, newChatId: () => "c1" });
  await app!.session.record("what is the capital of France", "Paris");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();

  const open = dom.find((n) => n.dataset["action"] === "open-chat");
  assert.ok(open, "no chat row");
  assert.match(open.textContent, /just now/, `no relative time on the row:\n${dom.text()}`);
  assert.match(
    open.getAttribute("aria-label") ?? "",
    /just now/,
    "the spoken name must carry the same time the row shows",
  );
  app?.dispose();
});

test("the WALL CLOCK is read through TimePort.epochMs, not Date.now", async () => {
  // `TimePort.epochMs` was implemented and conformance-tested and had zero
  // callers in the whole application: every wall-clock read in main.ts was a
  // bare `Date.now()`, so the seam that makes time injectable ran past its own
  // port. `now` is deliberately NOT passed here, which is the production path.
  const { dom, platform } = harness();
  const FIXED = 1_700_000_000_000;
  const timed: Platform = { ...platform, time: { ...platform.time, epochMs: () => FIXED } };
  const app = await mount({ root: dom.root as never, platform: timed, newChatId: () => "c1" });
  await app!.session.record("hello", "hi");
  const [chat] = await app!.session.list();
  assert.equal(chat?.updated, FIXED, "the chat's timestamp did not come from the port");
  app?.dispose();
});

test("streaming announcements are paced by the MONOTONIC clock, not the wall clock", async () => {
  // `announce` rate-limits with `nowMs - lastStreamAtMs >= ANNOUNCE_INTERVAL_MS`
  // -- an ELAPSED comparison, which `core/src/ports/time.ts` says in as many
  // words must use `nowMs` and never the wall clock: "Conflating them is how a
  // clock correction mid-stream makes a coalescer wait forever". main.ts passed
  // `Date.now()`, so an NTP correction moving the clock backwards mid-answer
  // silences every further streaming announcement until real time catches up
  // with the pre-correction reading, and a screen-reader user simply stops
  // being told what the model is saying.
  //
  // Driven here by a monotonic clock that advances a second per read against a
  // turn that never ends: with the port's clock BOTH finished sentences are
  // spoken during the stream, and with `Date.now()` the second one waits for a
  // terminal event that is not coming.
  const { dom, http, platform } = harness();
  let tick = 0;
  const timed: Platform = {
    ...platform,
    time: { ...platform.time, nowMs: () => (tick += 1000) },
  };
  http.on("/chat", () => ({
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: new ReadableStream<Uint8Array>({
      async start(controller) {
        const enc = new TextEncoder();
        controller.enqueue(enc.encode(sse([["start", { msg_id: "m1", run_id: "r1" }]])));
        controller.enqueue(enc.encode(sse([["delta", { msg_id: "m1", text: "The first sentence. " }]])));
        await new Promise((r) => setTimeout(r, 40));
        controller.enqueue(enc.encode(sse([["delta", { msg_id: "m1", text: "The second sentence. " }]])));
        // Never closed: an `end` would flush everything held back regardless
        // of which clock paced it, and the test would pass against the defect.
      },
    }),
  }));
  const app = await mount({ root: dom.root as never, platform: timed, now: () => 1, newChatId: () => "c1" });
  submit(dom, "two sentences please");
  await settle(200);

  // The region is REASSIGNED per publish (each utterance replaces the last),
  // so what it holds at the end is the most recent thing said. With the port's
  // clock that is the second sentence; rate-limited by the wall clock, the
  // second announcement never happens and the region still reads the first.
  const polite = dom.find((n) => n.getAttribute("aria-live") === "polite");
  assert.match(
    polite?.textContent ?? "",
    /second sentence/i,
    `the second sentence never reached the live region:\n${polite?.textContent}`,
  );
  app?.dispose();
});

// ---- the API key: entering one, and it reaching the engine -------------------
//
// The blocker this closes, measured on an Android emulator: the app launched,
// the in-process engine loaded, and the first turn failed with "The
// OPENAI_API_KEY environment variable is missing or empty; either provide it,
// or instantiate the OpenAI client with an apiKey option." Settings showed
// Engine and Engine address and nothing else. There was no field, and had there
// been one nothing read it back: `secrets.get` had zero non-test callers and
// the engine never received a key.

test("the settings screen has a MASKED field for the API key", async () => {
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);

  const field = keyField(dom);
  assert.ok(field, `there must be somewhere to put a key:\n${dom.text()}`);
  assert.equal(field.type, "password", "a credential typed in the clear is one a screenshot keeps");
  assert.equal(field.dataset["action"], "set-secret", "it must commit through the secret path");
  // Not `set-setting`: that path goes to StoragePort, which is the plaintext
  // settings file this whole split exists to keep keys out of.
  assert.notEqual(field.dataset["action"], "set-setting");
  await app?.dispose();
});

test("a pasted key reaches the KEYCHAIN and never the settings file", async () => {
  const storage = createFakeStorage();
  const { dom, platform, secrets } = harness({ storage });
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);

  const field = keyField(dom);
  field!.value = "sk-typed-by-a-user";
  dom.change(field as never);
  await settle();

  assert.equal(
    await secrets.get({ slot: "openai", account: "default" }),
    "sk-typed-by-a-user",
    "the key must actually be stored",
  );
  // And nothing was written to the plain store. store.ts quotes the failure
  // this prevents: "One reference app keyrings its API keys and then writes its
  // proxy password to the settings file."
  const contents: string[] = [];
  for (const key of storage.writes) {
    const raw = await storage.read(key);
    if (raw !== null) contents.push(raw);
  }
  assert.equal(
    contents.join("\n").includes("sk-typed-by-a-user"),
    false,
    `the key reached the plain settings file:\n${contents.join("\n")}`,
  );
  await app?.dispose();
});

test("the field is EMPTIED after a commit and the key is nowhere in the DOM", async () => {
  // The leak this closes is not hypothetical: `settingControl` seeds a plain
  // field from the store, and the mirror of that line on a secret row would put
  // the credential into every screenshot, crash report and accessibility dump
  // of this screen. The facade has no getter precisely so that line cannot be
  // written -- and the field must not hold what the user typed either.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);

  const field = keyField(dom);
  field!.value = "sk-should-not-linger";
  dom.change(field as never);
  await settle();

  assert.equal(field!.value, "", "the field must not hold the key after committing it");
  assert.equal(
    dom.text().includes("sk-should-not-linger"),
    false,
    `the key is rendered somewhere on the page:\n${dom.text()}`,
  );
  await app?.dispose();
});

test("re-opening Settings does not echo the stored key back into the field", async () => {
  // The other half: a screen rebuilt from the store must have nothing to draw
  // it FROM. This is the test that fails the day someone "helpfully" adds a
  // secret getter to the facade and uses it.
  const { dom, platform, secrets } = harness();
  await secrets.set({ slot: "openai", account: "default" }, "sk-already-stored");
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);

  assert.equal(keyField(dom)!.value, "", "a stored key must never be painted into the field");
  assert.equal(dom.text().includes("sk-already-stored"), false, dom.text());
  await app?.dispose();
});

test("the row says Configured from has(), without reading the value", async () => {
  // ports/secrets.ts rule 2: "`has()` exists so the UI can render 'configured'
  // without reading the value." A screen that answered this question with
  // `get()` would fault the credential into the render pass every time the user
  // opened Settings.
  const { dom, platform, secrets } = harness();
  await secrets.set({ slot: "openai", account: "default" }, "sk-already-stored");
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  const before = secrets.reads;
  await openSettings(dom);

  assert.equal(presenceOf(dom, "openaiApiKey"), "Configured");
  assert.equal(secrets.reads, before, "rendering presence must not read the secret's value");
  await app?.dispose();
});

test("with nothing stored the row says Not set -- the pair", async () => {
  // Without this, a row hard-wired to "Configured" would satisfy the test
  // above, and a user with no key would be told they have one.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);
  assert.equal(presenceOf(dom, "openaiApiKey"), "Not set");
  await app?.dispose();
});

test("presence flips to Configured as soon as a key is entered", async () => {
  // The row is the only confirmation the user gets -- the field empties itself,
  // so a row that still said "Not set" would read as a save that silently
  // failed, and the natural response is to paste it again.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);
  assert.equal(presenceOf(dom, "openaiApiKey"), "Not set");

  const field = keyField(dom);
  field!.value = "sk-fresh";
  dom.change(field as never);
  await settle();

  assert.equal(presenceOf(dom, "openaiApiKey"), "Configured");
  await app?.dispose();
});

test("a pasted key is trimmed, so a trailing newline is not part of the credential", async () => {
  // A key pasted out of a mail client or a terminal arrives with whitespace,
  // and the provider error it produces names the KEY rather than the
  // whitespace -- so the user concludes their key is bad.
  const { dom, platform, secrets } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);

  const field = keyField(dom);
  field!.value = "  sk-padded\n";
  dom.change(field as never);
  await settle();

  assert.equal(await secrets.get({ slot: "openai", account: "default" }), "sk-padded");
  await app?.dispose();
});

test("Remove takes the key back out, so 'no key' is a reachable state", async () => {
  // A key that can be entered and replaced but never removed leaves "not
  // configured" somewhere the user can never get back to -- and `clearSecret`
  // was another facade method with no caller outside tests.
  const { dom, platform, secrets } = harness();
  await secrets.set({ slot: "openai", account: "default" }, "sk-to-remove");
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await openSettings(dom);
  assert.equal(presenceOf(dom, "openaiApiKey"), "Configured");

  const remove = dom.find((n) => n.dataset["action"] === "clear-secret");
  assert.ok(remove, `there must be a way to remove a stored key:\n${dom.text()}`);
  dom.click(remove as never);
  await settle();

  assert.equal(await secrets.has({ slot: "openai", account: "default" }), false);
  assert.equal(presenceOf(dom, "openaiApiKey"), "Not set");
  await app?.dispose();
});

test("a keychain that REJECTS says so, and does not become the app-wide crash screen", async () => {
  // SecretsPort rejects on a real device: a locked keychain, a keystore that
  // will not open. Left to float, that rejection reaches the global crash
  // handler and replaces the WHOLE app with the fatal screen -- on the one
  // screen the user is trying to repair.
  const { dom, platform } = harness();
  const failing = {
    ...platform.secrets,
    async set(): Promise<void> {
      throw new Error("keystore is locked");
    },
  };
  const app = await mount({
    root: dom.root as never,
    platform: { ...platform, secrets: failing },
    now: () => 1,
    newChatId: () => "c1",
  });
  await openSettings(dom);

  const field = keyField(dom);
  field!.value = "sk-will-not-store";
  dom.change(field as never);
  await settle();

  assert.ok(
    dom.find((n) => n.className.includes("screen-settings")),
    "the settings screen must survive a keychain failure",
  );
  const note = dom.find((n) => n.dataset["settingError"] === "openaiApiKey");
  assert.ok(note !== null && note.textContent !== "", `a refused write must be said out loud:\n${dom.text()}`);
  assert.equal(note.hidden, false);
  await app?.dispose();
});

test("END TO END: a key entered in Settings authenticates the very next message", async () => {
  // The acceptance test. Everything above proves a piece; this drives the whole
  // path the user walks -- open Settings, paste a key, go back, send a message
  // -- through the shipping composition root, and asserts the credential
  // reached the agent that answers. A key stored and never used is the same bug
  // in a new place.
  const configs: { instructions: string; llm?: string; apiKey?: string }[] = [];
  class ScriptedAgent {
    lastStopReason: "completed" | null = "completed";
    constructor(config: { instructions: string; llm?: string; apiKey?: string }) {
      configs.push(config);
    }
    // Present because the engine CALLS it on every turn, and this class is
    // handed in through `loadAgent` as `never` -- so a missing member is not a
    // typecheck failure, it is "agent.setHistory is not a function" rendered
    // into the transcript where the answer should be.
    setHistory() {}
    async *streamEvents() {
      yield { type: "text", delta: "Paris." } as const;
      yield { type: "finish", text: "Paris." } as const;
    }
  }

  const { dom, http, platform: web } = harness();
  http.on("/chat", () => {
    throw new Error("the remote engine must not be contacted on a device");
  });
  // `kind: "tauri"` so the device default applies and the in-process engine is
  // what answers -- the engine that had no way to be given a key.
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
    loadAgent: async () => ScriptedAgent as never,
  });
  assert.equal(app?.engine.id, ENGINE_PRAISONAI_TS);

  await openSettings(dom);
  const field = keyField(dom);
  assert.ok(field, `no key field on the settings screen:\n${dom.text()}`);
  field.value = "sk-end-to-end";
  dom.change(field as never);
  await settle();

  // Back to the chat and ask something.
  dom.click(dom.find((n) => n.dataset["route"] === "chat") as never);
  await settle();
  submit(dom, "capital of france?");
  await settle(120);

  assert.equal(configs.length, 1, "one Agent, built on the turn -- not at boot");
  assert.equal(
    configs[0]?.apiKey,
    "sk-end-to-end",
    "the key the user entered must authenticate the agent that answers",
  );
  const answer = dom.find((n) => n.textContent.includes("Paris") && n.className.includes("row"));
  assert.ok(answer, `the answer must reach the transcript:\n${dom.text()}`);
  assert.equal(dom.find((n) => n.className.includes("row-error")), null, "and nothing must fail on the way");
  // And the key is still not anywhere on the page.
  assert.equal(dom.text().includes("sk-end-to-end"), false, dom.text());
  await app?.dispose();
});

// ---- conversation memory, through the shipping composition root -------------
//
// engine.test.ts proves the engine restores whatever history it is handed;
// session.test.ts proves the session projects one. Neither proves the two are
// connected in the app that ships, and "both halves built, nothing joining
// them" is exactly how this package lost `record()` once already. These drive
// the real mount, the real controller, the real session and the real in-process
// engine -- only the Agent class is scripted, through the seam appEngines
// exposes for it.

/** An Agent class that records the conversation it was restored with, per turn. */
function rememberingAgentClass(answers: readonly string[]): {
  readonly module: unknown;
  readonly histories: { role: string; content: string }[][];
  readonly prompts: string[];
} {
  const histories: { role: string; content: string }[][] = [];
  const prompts: string[] = [];
  let turn = 0;
  class Remembering {
    lastStopReason: "completed" | null = "completed";
    private restored: { role: string; content: string }[] = [];
    setHistory(messages: readonly { role: string; content: string }[]) {
      this.restored = messages.map((m) => ({ role: m.role, content: m.content }));
    }
    async *streamEvents(prompt: string) {
      histories.push(this.restored);
      prompts.push(prompt);
      const text = answers[Math.min(turn++, answers.length - 1)] ?? "";
      yield { type: "finish", text } as const;
    }
  }
  return { module: Remembering, histories, prompts };
}

test("ACCEPTANCE: a follow-up question reaches the model WITH the turn before it", async () => {
  // The defect, stated as the user experiences it: ask for the capital of
  // France, get "Paris", ask "And its population?" -- and the second question
  // used to arrive at the provider with no subject at all, so the honest reply
  // was a request for clarification rather than a number.
  const { module, histories, prompts } = rememberingAgentClass([
    "Paris.",
    "About 2.1 million.",
  ]);
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
    loadAgent: async () => module as never,
  });
  assert.equal(app?.engine.id, ENGINE_PRAISONAI_TS);

  submit(dom, "What is the capital of France?");
  await settle(120);
  submit(dom, "And its population?");
  await settle(120);

  assert.deepEqual(prompts, ["What is the capital of France?", "And its population?"]);
  assert.deepEqual(histories[0], [], "the first question has nothing behind it");
  assert.deepEqual(
    histories[1],
    [
      { role: "user", content: "What is the capital of France?" },
      { role: "assistant", content: "Paris." },
    ],
    "the follow-up must carry the exchange it follows",
  );
  await app?.dispose();
});

test("ACCEPTANCE: a conversation REOPENED after a relaunch still has its memory", async () => {
  // Force-stop, relaunch, reopen from the chat list, ask a follow-up. A
  // history assembled from turns seen in the current process passes the case
  // above and fails this one -- and this is the case a phone hits every day,
  // because a phone kills backgrounded apps.
  const storage = createFakeStorage();

  const first = rememberingAgentClass(["Paris."]);
  const one = harness({ storage });
  const app1 = await mount({
    root: one.dom.root as never,
    platform: { ...one.platform, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
    loadAgent: async () => first.module as never,
  });
  submit(one.dom, "What is the capital of France?");
  await settle(120);
  await app1?.dispose();

  // A second launch over the same disk. Nothing survives in memory.
  const second = rememberingAgentClass(["About 2.1 million."]);
  const two = harness({ storage });
  const app2 = await mount({
    root: two.dom.root as never,
    platform: { ...two.platform, kind: "tauri" },
    now: () => 2,
    newChatId: () => "c-fresh",
    loadAgent: async () => second.module as never,
  });

  two.dom.click(two.dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  const row = two.dom.find((n) => n.dataset["action"] === "open-chat");
  assert.ok(row, `the stored chat must be listed:\n${two.dom.text()}`);
  two.dom.click(row as never);
  await settle();

  submit(two.dom, "And its population?");
  await settle(120);

  assert.deepEqual(second.prompts, ["And its population?"]);
  assert.deepEqual(
    second.histories[0],
    [
      { role: "user", content: "What is the capital of France?" },
      { role: "assistant", content: "Paris." },
    ],
    "a reopened conversation must contribute its stored history",
  );
  await app2?.dispose();
});

test("New chat starts the model with a blank memory, not the previous conversation", async () => {
  // The pair. A history that is merely "everything ever recorded" would leak
  // the abandoned conversation into a chat the user believes is empty.
  const { module, histories } = rememberingAgentClass(["Paris.", "second answer"]);
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
    loadAgent: async () => module as never,
  });

  submit(dom, "What is the capital of France?");
  await settle(120);
  dom.click(dom.find((n) => n.dataset["action"] === "new-chat") as never);
  await settle();
  submit(dom, "an unrelated question");
  await settle(120);

  assert.deepEqual(histories[1], [], `the new chat must start empty:\n${JSON.stringify(histories)}`);
  await app?.dispose();
});

// ---- your own message, on screen --------------------------------------------
//
// The plainest defect the app had: you typed, tapped Send, and only the reply
// appeared. `ui/src/transcript/view-model.ts` defined seven row kinds and not
// one of them was the user, so there was nothing for any renderer to draw.
// These drive the whole composition root -- composer, controller, reducer, view
// model, reconciler, DOM -- because every layer below was individually correct
// and the conversation still came out with one side missing.

/** The transcript's rows, in order, as `kind|text` so ORDER can be asserted. */
const transcriptRows = (dom: ReturnType<typeof createFakeDom>): string[] => {
  const transcript = dom.find((n) => n.className.includes("transcript"));
  assert.ok(transcript, "no transcript");
  return (transcript.children as { className: string; textContent: string }[]).map(
    (c) => `${c.className}|${c.textContent}`,
  );
};

test("your own message appears in the transcript, above the reply", async () => {
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "Paris." }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.notEqual(app, null);

  submit(dom, "what is the capital of France");
  await settle(120);

  const rows = transcriptRows(dom);
  const mine = rows.findIndex((r) => r.startsWith("row row-user"));
  assert.notEqual(mine, -1, `the user's own message never rendered:\n${rows.join("\n")}`);
  assert.match(rows[mine] ?? "", /what is the capital of France/);

  // Above the answer, which is the only thing that says which reply belongs to
  // which question once the conversation is longer than one turn.
  const reply = rows.findIndex((r) => r.startsWith("row row-text") && r.includes("Paris."));
  assert.notEqual(reply, -1, `the reply never rendered:\n${rows.join("\n")}`);
  assert.ok(mine < reply, `the question must render above its answer:\n${rows.join("\n")}`);
  app?.dispose();
});

test("a send the composer REFUSES leaves nothing on screen", async () => {
  // The optimistic-vs-confirmed rule, end to end: a message that was never sent
  // must not be sitting in the transcript looking sent. The composer refuses a
  // second submit while a turn is in flight (composer.ts rule 1) and that
  // refusal must be total -- the row is seeded when a run is ISSUED, so a
  // refused submit produces no turn and therefore no row.
  const { dom, http, platform } = harness();
  // A stream held OPEN between frames, so the turn is genuinely still running
  // when the second submit arrives. `sseResponse` delivers everything at once,
  // which would let the first turn finish and make the second submit a
  // perfectly ordinary send.
  const frames = sse([
    ["start", { msg_id: "m1", run_id: "r1" }],
    ["delta", { msg_id: "m1", text: "first answer" }],
    ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
  ]).split(/(?<=\n\n)/).filter((f) => f !== "");
  http.on("/chat", () => ({
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: new ReadableStream<Uint8Array>({
      async pull(controller) {
        const next = frames.shift();
        if (next === undefined) return controller.close();
        await new Promise((r) => setTimeout(r, 150));
        controller.enqueue(new TextEncoder().encode(next));
      },
    }),
  }));
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "the one I sent");
  // Long enough for `start` to arrive and the button to become Stop.
  await settle(250);
  const stopping = dom.find((n) => n.dataset["action"] === "stop");
  assert.ok(stopping, "the turn was not still running -- the refusal path is untested");
  submit(dom, "REFUSED-while-busy");
  await settle(500);

  const all = transcriptRows(dom).join("\n");
  assert.match(all, /the one I sent/, `the sent message must be on screen:\n${all}`);
  assert.equal(
    all.includes("REFUSED-while-busy"),
    false,
    `a message the composer refused was painted as though it had been sent:\n${all}`,
  );
  app?.dispose();
});

test("a turn that FAILED keeps the message on screen and says it was not saved", async () => {
  // The other half of the same rule. The message WAS sent -- the engine got it
  // and answered 401 -- so removing it would hide the question the error is
  // about. But `end.userIndex` never arrived, so it is not in the stored
  // conversation and the row must not imply that it is.
  const { dom, http, platform } = harness();
  http.on("/chat", () => ({ ok: false, status: 401, headers: {}, body: streamOf("nope") }));
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "a question nobody answered");
  await settle(150);

  const rows = transcriptRows(dom);
  const mine = rows.find((r) => r.startsWith("row row-user"));
  assert.ok(mine, `a failed turn must still show what was asked:\n${rows.join("\n")}`);
  assert.match(mine, /a question nobody answered/);
  assert.match(mine, /not saved/i, `a message that reached no disk must say so:\n${mine}`);
  app?.dispose();
});

test("a REOPENED conversation shows the user's messages as the USER's", async () => {
  // `historyRows` mapped both roles to a `text` row -- the kind that means "the
  // model said this" -- so a reopened conversation painted the user's questions
  // in the assistant's clothes. The two sides were rendered identically and a
  // screen reader heard one voice. The prompt is ALREADY on disk with its role;
  // it was the role that was being discarded.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await app!.session.record("what is the capital of France", "Paris");

  dom.click(dom.find((n) => n.dataset["route"] === "chats") as never);
  await settle();
  dom.click(dom.find((n) => n.dataset["action"] === "open-chat") as never);
  await settle();

  const rows = transcriptRows(dom);
  const mine = rows.findIndex((r) => r.startsWith("row row-user"));
  assert.notEqual(mine, -1, `the reopened conversation showed no user message:\n${rows.join("\n")}`);
  assert.match(rows[mine] ?? "", /what is the capital of France/);
  // And the reply is still the assistant's, in order.
  const reply = rows.findIndex((r) => r.startsWith("row row-text") && r.includes("Paris"));
  assert.notEqual(reply, -1, `the stored answer was lost:\n${rows.join("\n")}`);
  assert.ok(mine < reply, `a reopened conversation must read in order:\n${rows.join("\n")}`);
  // The question must NOT be painted as model output.
  assert.equal(
    (rows[mine] ?? "").startsWith("row row-text"),
    false,
    "the user's stored message was rendered as the assistant's",
  );
  app?.dispose();
});

test("a finished turn stays on screen when the NEXT one begins", async () => {
  // The controller publishes only the CURRENT turn and resets it per run, so
  // the reconciler saw the previous turn's ids missing and removed every one of
  // them. Measured on main: after a second Send the transcript contained the
  // second answer and nothing else -- the first question and its reply gone
  // from a conversation that was still open. Invisible while there were no user
  // rows (one anonymous paragraph replacing another) and glaring with them.
  const { dom, http, platform } = harness();
  let n = 0;
  http.on("/chat", () => {
    n += 1;
    const id = `m${n}`;
    return sseResponse(
      sse([
        ["start", { msg_id: id, run_id: `r${n}` }],
        ["delta", { msg_id: id, text: `ANSWER-${n}` }],
        ["end", { msg_id: id, user_index: 2 * n - 2, assistant_index: 2 * n - 1, versions: 1, active: 0 }],
      ]),
    );
  });
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });

  submit(dom, "QUESTION-1");
  await settle(150);
  submit(dom, "QUESTION-2");
  await settle(150);

  const rows = transcriptRows(dom);
  const at = (needle: string): number => {
    const i = rows.findIndex((r) => r.includes(needle));
    assert.notEqual(i, -1, `"${needle}" is not on screen:\n${rows.join("\n")}`);
    return i;
  };
  // All four, in the order they happened.
  assert.ok(at("QUESTION-1") < at("ANSWER-1"), `turn 1 is out of order:\n${rows.join("\n")}`);
  assert.ok(at("ANSWER-1") < at("QUESTION-2"), `turn 1 was erased by turn 2:\n${rows.join("\n")}`);
  assert.ok(at("QUESTION-2") < at("ANSWER-2"), `turn 2 is out of order:\n${rows.join("\n")}`);
  // And nothing was drawn twice: promotion must move a turn, not copy it.
  assert.equal(rows.filter((r) => r.includes("QUESTION-1")).length, 1, "the first question rendered twice");
  app?.dispose();
});

test("New chat clears the finished turns too, not just the live one", async () => {
  // The promotion above gives the screen a second place a previous
  // conversation can hide in. `setChat` clears the controller's turn; it cannot
  // know about rows the app promoted, so New chat has to drop those as well or
  // the "fresh" chat opens on the last one.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "an answer" }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  submit(dom, "the old conversation");
  await settle(150);
  assert.match(transcriptRows(dom).join("\n"), /the old conversation/);

  dom.click(dom.find((n) => n.dataset["action"] === "new-chat") as never);
  await settle(60);
  assert.equal(
    transcriptRows(dom).join("\n").includes("the old conversation"),
    false,
    "a new chat opened on the previous conversation's messages",
  );
  app?.dispose();
});

// ---- the transcript and the model's memory, held to each other ---------------
//
// Two "histories" meet in `mount` and they are NOT the same list. #4816 replays
// `Session.current()` onto a fresh agent every turn -- only what `record()`
// actually wrote. This PR keeps every finished turn on screen, written or not,
// because a question you asked and the error that answered it both belong in
// the transcript.
//
// So they can legitimately differ, and the danger is that they differ SILENTLY:
// a turn rendered as though it were part of the conversation while the model
// has never heard of it. These pin the agreement in both directions, and pin
// the one divergence to the row that announces itself.

/** An Agent that records the history it was restored with and fails one turn. */
function agentFailingTurn(failOn: number, answers: readonly string[]): {
  readonly module: unknown;
  readonly histories: { role: string; content: string }[][];
} {
  const histories: { role: string; content: string }[][] = [];
  let turn = 0;
  class Flaky {
    lastStopReason: "completed" | null = "completed";
    private restored: { role: string; content: string }[] = [];
    setHistory(messages: readonly { role: string; content: string }[]): void {
      this.restored = messages.map((m) => ({ role: m.role, content: m.content }));
    }
    async *streamEvents(
      _prompt: string,
    ): AsyncGenerator<{ type: "text"; delta: string } | { type: "finish"; text: string }> {
      histories.push(this.restored);
      const mine = turn++;
      if (mine === failOn) throw new Error("the provider dropped the connection");
      const text = answers[mine] ?? "";
      // The DELTA as well as the finish. An agent that only ever yields
      // `finish` produces a turn with no text, which `finish()` in
      // transcript.ts correctly turns into error{empty} -- so the transcript
      // would be all error rows and the assertions below would be measuring
      // the harness rather than the app.
      yield { type: "text", delta: text } as const;
      yield { type: "finish", text } as const;
    }
  }
  return { module: Flaky, histories };
}

/** The user rows on screen, as `state|text`. */
const userRowsOnScreen = (dom: ReturnType<typeof createFakeDom>): string[] => {
  const transcript = dom.find((n) => n.className.includes("transcript"));
  assert.ok(transcript, "no transcript");
  return (transcript.children as { className: string; textContent: string; dataset: Record<string, string> }[])
    .filter((c) => c.className.includes("row-user"))
    .map((c) => `${c.dataset["state"]}|${c.textContent}`);
};

test("every turn the model is told about is on screen, in the same order", async () => {
  // The agreeing direction. `Session.current()` is what the engine replays and
  // what `historyRows` paints on reopen, so a stored turn cannot be in one and
  // missing from the other -- and the promoted rows must not reorder it.
  const { module, histories } = agentFailingTurn(-1, ["Paris.", "About 2.1 million."]);
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
    loadAgent: async () => module as never,
  });

  submit(dom, "What is the capital of France?");
  await settle(120);
  submit(dom, "And its population?");
  await settle(120);

  // What the model was told on the second turn...
  const told = histories[1] ?? [];
  assert.deepEqual(
    told,
    [
      { role: "user", content: "What is the capital of France?" },
      { role: "assistant", content: "Paris." },
    ],
    "the follow-up must carry the exchange it follows",
  );

  // ...must all be on screen, in that order. Not "present somewhere": a
  // transcript that shows the same turns in a different order than the model
  // was given them is a conversation the two parties remember differently.
  const shown = transcriptRows(dom);
  let cursor = -1;
  for (const message of told) {
    const at = shown.findIndex((r, i) => i > cursor && r.includes(message.content));
    assert.notEqual(at, -1, `the model was told "${message.content}" and the screen never showed it:\n${shown.join("\n")}`);
    cursor = at;
  }
  // And every user row that claims to be stored is one the model has.
  assert.deepEqual(
    userRowsOnScreen(dom).filter((r) => r.startsWith("stored|")).map((r) => r.slice("stored|".length)),
    ["You said:What is the capital of France?", "You said:And its population?"],
    "a row claiming to be stored must be a turn that was really written",
  );
  await app?.dispose();
});

test("a turn the model was NEVER told about is the one row that says it was not saved", async () => {
  // The diverging direction, and the reason the divergence is allowed. The
  // second turn fails, so `record()` is never called and the model is never
  // told -- but the question stays on screen above the error explaining what
  // happened to it. What must NOT happen is that it looks like an ordinary,
  // remembered message: the row is `unstored` and says so in words.
  const { module, histories } = agentFailingTurn(1, ["Paris.", "", "Still here."]);
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
    loadAgent: async () => module as never,
  });

  submit(dom, "remembered question");
  await settle(120);
  submit(dom, "LOST-QUESTION");
  await settle(150);
  submit(dom, "third question");
  await settle(150);

  // All three are on screen -- the failed one is not swept away.
  const rows = userRowsOnScreen(dom);
  assert.equal(rows.length, 3, `every question asked belongs on screen:\n${rows.join("\n")}`);
  assert.match(rows[1] ?? "", /LOST-QUESTION/);

  // The failed one, and ONLY the failed one, is marked not-saved.
  assert.ok((rows[0] ?? "").startsWith("stored|"), `turn 1 was written and must say so: ${rows[0]}`);
  assert.ok((rows[1] ?? "").startsWith("unstored|"), `turn 2 was never written: ${rows[1]}`);
  assert.ok((rows[2] ?? "").startsWith("stored|"), `turn 3 was written: ${rows[2]}`);
  assert.match(rows[1] ?? "", /not in the stored conversation/i);

  // And the model, on the third turn, was told about turn 1 and NOT turn 2.
  const told = histories[2] ?? [];
  assert.deepEqual(
    told,
    [
      { role: "user", content: "remembered question" },
      { role: "assistant", content: "Paris." },
    ],
    `the model must be told exactly what was stored:\n${JSON.stringify(told)}`,
  );
  assert.equal(
    JSON.stringify(told).includes("LOST-QUESTION"),
    false,
    "a turn that was never stored must not reach the model",
  );
  await app?.dispose();
});

test("the first render takes the boot indicator away", async () => {
  // The other half of the boot screen (app/src/boot-screen.test.ts asserts the
  // markup and the styling). `app/index.html` paints a wordmark and "Starting…"
  // into #root before any module runs, so a cold start is not a blank page --
  // and the ONE thing that must never happen is that it survives the first
  // render and sits on top of the app.
  //
  // Nothing removes it by name. `mount` clears #root before appending the chat
  // screen, which is what makes the guarantee total: whatever the page painted
  // ahead of the app is gone in the same statement pair that puts the real UI
  // there. This test is what stops that clear from being "simplified" away --
  // the app would still look correct on every screen a test drives, because
  // every other test starts from an empty root.
  const { dom, platform } = harness();
  const boot = dom.make("div");
  boot.className = "boot";
  boot.dataset["boot"] = "";
  const mark = dom.make("p");
  mark.textContent = "PraisonAI";
  boot.append(mark);
  dom.root.append(boot);
  assert.ok(dom.find((n) => n.dataset["boot"] !== undefined) !== null, "the fixture must start with one");

  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  assert.equal(
    dom.find((n) => n.dataset["boot"] !== undefined),
    null,
    "the boot indicator must not survive the first render",
  );
  // And the real UI is what replaced it, rather than the root simply being
  // emptied -- an indicator removed with nothing put in its place would pass
  // the assertion above while showing the blank page this all exists to fix.
  assert.ok(dom.find((n) => n.tagName === "TEXTAREA") !== null, "the composer replaced it");
  await app?.dispose();
});

// ---- the empty chat screen, through the composition root --------------------
//
// Defects #3 and #8 were one screen: on a fresh launch the app rendered a
// header, several hundred pixels of nothing, and a Send button, and the only
// thing that ever mentioned the API key it cannot work without was the provider
// SDK, after a message had been sent, in the words "The OPENAI_API_KEY
// environment variable is missing or empty".
//
// `ui/src/transcript/empty-state.test.ts` owns the decision; these own the
// WIRING, which is where every defect this file has ever found actually lived:
// a pure function that is right and a composition root that calls it wrongly,
// or not at all.

/** The empty-state panel, or null when the app never built one. */
const emptyPanel = (dom: ReturnType<typeof createFakeDom>) =>
  dom.find((n) => n.className === "empty-state");

/** The panel's words, or "" when it is absent or hidden -- which is what the
 *  user sees in either case. */
const emptyWords = (dom: ReturnType<typeof createFakeDom>): string => {
  const panel = emptyPanel(dom);
  return panel === null || panel.hidden ? "" : panel.textContent;
};

test("a fresh install is told it needs a key, on the first screen", async () => {
  // Defect #3, end to end. `kind: "tauri"` is the device default, so the
  // in-process engine is what would answer -- the engine that cannot answer
  // anything without a key. Nothing is stored in the fake keychain.
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  // The keychain lookup is async; the guidance appears when it lands.
  await settle();

  const panel = emptyPanel(dom);
  assert.ok(panel, `no empty state was built at all:\n${dom.text()}`);
  assert.equal(panel.hidden, false, "the empty state must be on screen for a fresh install");
  assert.ok(emptyWords(dom).includes(en.emptyNeedsKeyTitle), emptyWords(dom));
  assert.ok(emptyWords(dom).includes(en.emptyNeedsKeyBody), emptyWords(dom));
  await app?.dispose();
});

test("the key guidance offers a tap through to Settings", async () => {
  // Saying a key is needed and leaving the user to find the screen that takes
  // one is the same defect one step softer. The button goes through the SAME
  // `navigate` intent every other route button does, so this asserts the screen
  // actually changes rather than that a button exists.
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  await settle();

  const panel = emptyPanel(dom);
  assert.ok(panel);
  const button = panel.children.find((c) => c.tagName === "BUTTON");
  assert.ok(button, `the guidance has no way out of it:\n${panel.textContent}`);
  assert.equal(button.hidden, false);
  assert.equal(button.dataset["route"], "settings");

  dom.click(button as never);
  await settle();
  assert.ok(keyField(dom), `tapping the guidance did not reach Settings:\n${dom.text()}`);
  await app?.dispose();
});

test("a device with a key stored is welcomed, not told to configure the app", async () => {
  // The mutation this kills: showing the "needs a key" copy when a key IS set.
  // Same platform, same engine, one difference -- and it is the state a
  // returning user meets on every new chat for the life of the install.
  const { dom, platform: web, secrets } = harness();
  await secrets.set({ slot: "openai", account: "default" }, "sk-already-stored");
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  await settle();

  const words = emptyWords(dom);
  assert.ok(words.includes(en.emptyTranscript), words);
  assert.ok(words.includes(en.emptyAbout), words);
  assert.equal(words.includes(en.emptyNeedsKeyTitle), false, "a configured user must not be told to configure");
  const button = emptyPanel(dom)?.children.find((c) => c.tagName === "BUTTON");
  assert.equal(button?.hidden, true, "there is nothing to fix, so there is no button");
  await app?.dispose();
});

test("pasting a key in Settings clears the guidance from the chat behind it", async () => {
  // The transition, which is the whole point of the guidance: the user does the
  // one thing it asks and the screen it came from stops asking. A panel that
  // only re-reads the keychain at boot would still be demanding a key on the
  // chat screen immediately after one was saved.
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  await settle();
  assert.ok(emptyWords(dom).includes(en.emptyNeedsKeyTitle), "precondition: the guidance is up");

  await openSettings(dom);
  const field = keyField(dom);
  assert.ok(field);
  field.value = "sk-pasted";
  dom.change(field as never);
  await settle();

  const words = emptyWords(dom);
  assert.equal(words.includes(en.emptyNeedsKeyTitle), false, `still demanding a key:\n${words}`);
  assert.ok(words.includes(en.emptyTranscript), words);
  await app?.dispose();
});

test("the empty state goes the moment the transcript has anything in it", async () => {
  // Defect #8's other half, and the constraint that matters most: the panel
  // must not fight the user/assistant rows. `publish` is the one place rows
  // arrive, so this drives a real turn over the fake transport rather than
  // poking the DOM.
  const { dom, http, platform } = harness();
  http.on("/chat", () =>
    sseResponse(
      sse([
        ["start", { msg_id: "m1", run_id: "r1" }],
        ["delta", { msg_id: "m1", text: "Paris." }],
        ["end", { msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 }],
      ]),
    ),
  );
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await settle();
  assert.notEqual(emptyWords(dom), "", "precondition: an empty chat says something");

  submit(dom, "capital of france?");
  await settle(120);

  assert.equal(emptyPanel(dom)?.hidden, true, `the empty state survived a conversation:\n${dom.text()}`);
  // And the rows it was standing in for are there instead.
  assert.ok(dom.find((n) => n.className.includes("row-user")), "the user's message must be on screen");
  assert.ok(dom.text().includes("Paris."), dom.text());

  // New chat empties the transcript, so the empty state comes back -- the same
  // three resets that clear the rows must not leave a blank rectangle behind.
  dom.click(dom.find((n) => n.dataset["action"] === "new-chat") as never);
  await settle();
  assert.equal(emptyPanel(dom)?.hidden, false, `New chat left a blank screen:\n${dom.text()}`);
  assert.ok(emptyWords(dom).includes(en.emptyTranscript), emptyWords(dom));
  await app?.dispose();
});

test("the empty chat is announced, so it is not silent to a screen reader", async () => {
  // An empty transcript is a `role="log"` with nothing in it. Without this the
  // one screen a new user lands on has nothing at all to say to them.
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  await settle();

  const polite = dom.find((n) => n.getAttribute("aria-live") === "polite");
  assert.ok(polite);
  assert.ok(polite.textContent.includes(en.emptyNeedsKeyTitle), `polite region said "${polite.textContent}"`);
  // The way out is in the sentence, not three tab stops away.
  assert.ok(polite.textContent.includes(en.recoveryLabel("settings")), polite.textContent);
  await app?.dispose();
});

test("the empty state is a named landmark, not an unlabelled block", async () => {
  // `aria-labelledby` and NOT `aria-label`: a label on a container replaces its
  // contents in the accessibility tree (a11y/names.ts rule 3), which would cost
  // the reader the sentence and the button. A landmark pointing at an id that
  // does not exist has no name at all, so the pair is asserted together.
  const { dom, platform: web } = harness();
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  await settle();

  const panel = emptyPanel(dom);
  assert.ok(panel);
  assert.equal(panel.getAttribute("role"), "region");
  assert.equal(panel.getAttribute("aria-label"), null, "a label here would hide the panel's own words");
  const labelledBy = panel.getAttribute("aria-labelledby");
  assert.equal(labelledBy, EMPTY_TITLE_ID);
  const heading = dom.find((n) => n.getAttribute("id") === labelledBy);
  assert.ok(heading, "the landmark names an element that does not exist");
  assert.equal(heading.textContent, en.emptyNeedsKeyTitle);
  await app?.dispose();
});

test("presence is read with has(), never by faulting the key into the screen", async () => {
  // ports/secrets.ts rule 2, applied to the new caller. The chat screen asks
  // "is one configured?" and must not be able to answer it with `get()` -- and
  // the value must never reach the rendered text, where a screenshot or a crash
  // dump would pick it up.
  const { dom, platform: web, secrets } = harness();
  await secrets.set({ slot: "openai", account: "default" }, "sk-must-not-be-rendered");
  const before = secrets.reads;
  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  await settle();

  assert.equal(secrets.reads, before, "the empty state must ask presence, not read the value");
  assert.equal(dom.text().includes("sk-must-not-be-rendered"), false);
  await app?.dispose();
});

test("the boot indicator is gone before the empty state arrives -- neither, nor both", async () => {
  // The one interaction between this change and #4845 worth pinning rather than
  // assuming. `app/index.html` paints a wordmark and "Starting…" into #root on
  // the first frame; `mount` clears #root and appends the chat screen in the
  // same statement pair. The empty state lives INSIDE that screen, so it can
  // only arrive with the swap -- never beside the indicator, and never leaving a
  // frame with nothing on it.
  //
  // Both halves are asserted together, because either alone passes over the
  // failure: "the indicator is gone" is satisfied by an app that renders
  // nothing, and "the panel is up" is satisfied by an app that painted it
  // underneath a leftover boot screen.
  const { dom, platform: web } = harness();
  const boot = dom.make("div");
  boot.className = "boot";
  boot.dataset["boot"] = "";
  dom.root.append(boot);

  const app = await mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });
  await settle();

  assert.equal(
    dom.find((n) => n.dataset["boot"] !== undefined),
    null,
    "the boot indicator must not survive alongside the empty state",
  );
  assert.equal(emptyPanel(dom)?.hidden, false, `nothing replaced the boot indicator:\n${dom.text()}`);
  assert.ok(emptyWords(dom).includes(en.emptyNeedsKeyTitle), emptyWords(dom));
  // And the indicator's own words are not still on the page under another name.
  assert.equal(dom.text().includes("Starting"), false, dom.text());
  await app?.dispose();
});

test("an engine that needs no key never asks for one", async () => {
  // The web default is the remote engine, which authenticates at the server it
  // talks to. Telling its user to paste an OpenAI key sends them to configure a
  // credential nothing on this device reads.
  const { dom, platform } = harness();
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await settle();

  const words = emptyWords(dom);
  assert.notEqual(words, "", "an empty chat still has to say something");
  assert.equal(words.includes(en.emptyNeedsKeyTitle), false, words);
  assert.ok(words.includes(en.emptyAbout), words);
  await app?.dispose();
});

test("the guidance follows the engine IN FORCE, not the engineId setting", async () => {
  // The engine is selected once at boot and the controller holds that instance:
  // switching `engineId` in Settings changes the setting but not the engine
  // answering until the next launch. So the panel must read `app.engine.id` --
  // the engine actually handling prompts -- and not the live setting, or it
  // describes an engine other than the one the user's next message hits.
  //
  // Measured before the fix, the other way round: on a device with no key the
  // guidance was up, setting `engineId` to the remote engine dropped it, and
  // `app.engine.id` was still `praisonai-ts` -- so the app said no key was
  // needed and the next message went to the engine that needs one.
  const { dom, platform } = harness(); // web default: the remote engine is in force
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await settle();
  assert.equal(app?.engine.id, ENGINE_REMOTE_HTTP, "precondition: the remote engine is answering");
  assert.equal(emptyWords(dom).includes(en.emptyNeedsKeyTitle), false, "precondition: no key demanded");

  // Flip the persisted engine choice under the panel. The running engine does
  // not change, so the guidance must not either.
  await app!.settings.set("engineId", ENGINE_PRAISONAI_TS);
  await settle();

  // Then force a repaint through a path the user actually has. Asserting
  // straight after the `set` would prove nothing: nothing repaints the panel on
  // a settings write, so a version reading the SETTING would also still show
  // the welcome here and the test would pass over the bug. New chat re-runs the
  // empty state, which is where a wrong source of truth becomes visible.
  dom.click(dom.find((n) => n.dataset["action"] === "new-chat") as never);
  await settle();

  assert.equal(app?.engine.id, ENGINE_REMOTE_HTTP, "the engine in force must not have changed mid-session");
  const words = emptyWords(dom);
  assert.equal(
    words.includes(en.emptyNeedsKeyTitle),
    false,
    `the panel demanded a key for an engine that is not the one running:\n${words}`,
  );
  await app?.dispose();
});

test("clearing a key while Settings is open is announced on return to chat", async () => {
  // The polite region lives inside the chat screen, which is `hidden` while
  // Settings is on top -- and a hidden element is out of the accessibility tree
  // entirely, so a key removed there changes the empty state to needs-key
  // against a region nobody is listening to. Marking it announced in that
  // window would leave the "you now need a key" transition permanently
  // unspoken. It must be said the moment chat is visible again -- reached here
  // through the OS Back gesture, which is how a user returns from Settings.
  const shell = createFakeShell(PHONE_INSETS);
  const dom = createFakeDom();
  const secrets = createFakeSecrets();
  const platform: Platform = {
    shell, storage: createFakeStorage(), secrets,
    http: createFakeHttp(), time: nodeTime(), kind: "tauri",
  };
  await secrets.set({ slot: "openai", account: "default" }, "sk-already-stored");
  const app = await mount({ root: dom.root as never, platform, now: () => 1, newChatId: () => "c1" });
  await settle();
  assert.equal(emptyWords(dom).includes(en.emptyNeedsKeyTitle), false, "precondition: welcomed, not demanding");

  // Open Settings (chat screen hidden) and remove the key there.
  dom.click(dom.find((n) => n.dataset["route"] === "settings") as never);
  await settle();
  const chatScreen = dom.find((n) => n.className === "screen");
  assert.equal(chatScreen?.hidden, true, "precondition: the chat screen is hidden behind Settings");
  const remove = dom.find((n) => n.dataset["action"] === "clear-secret");
  assert.ok(remove, `no way to remove the key:\n${dom.text()}`);
  dom.click(remove as never);
  await settle();

  // THE DISCRIMINATING ASSERTION, and the reason this test is not just "the
  // region ends up with the right words in it". A live region announces on
  // CHANGE; a change made while the region sits in a hidden subtree is heard by
  // nobody and is not replayed when the subtree is shown again. So writing the
  // guidance here would look identical at the end of the test and be silent in
  // practice -- measured: removing the `screen.hidden` guard left every
  // assertion below passing. What has to be true is that the region is still
  // holding its PREVIOUS text at this point.
  const polite = dom.find((n) => n.getAttribute("aria-live") === "polite");
  assert.ok(polite);
  assert.equal(
    polite.textContent.includes(en.emptyNeedsKeyTitle),
    false,
    `announced into a hidden screen, where no reader hears it: "${polite.textContent}"`,
  );

  // Back to the chat. The empty state is now needs-key, and it must be spoken
  // -- not silently swallowed while the screen was hidden.
  shell.pressBack();
  await settle();

  assert.equal(chatScreen?.hidden, false, "the chat screen must be visible again after Back");
  assert.ok(emptyWords(dom).includes(en.emptyNeedsKeyTitle), `the guidance did not return:\n${dom.text()}`);
  assert.ok(
    polite.textContent.includes(en.emptyNeedsKeyTitle),
    `the needs-key transition was never announced:\n${polite.textContent}`,
  );
  await app?.dispose();
});

test("the chrome is never a blank rectangle, not even while boot is still running", async () => {
  // The window #4845's boot indicator cannot cover. `mount` appends the chrome
  // and THEN awaits `bootOrFail`; the indicator was retired by the
  // `root.textContent = ""` in that same statement pair, so between the two the
  // screen is a header, an empty middle and a Send button -- defect #8 exactly.
  // Measured on an Android 35 emulator before this: 117ms of it on a cold
  // start, 3.928s to 4.045s.
  //
  // Asserted with NO await at all. Everything up to `bootOrFail` is
  // synchronous, so the panel has to be on screen the instant `mount` yields --
  // which is what makes this a test of the seed and not of the post-boot
  // refresh. A single `await` here would let boot finish and the test would
  // pass without the seed existing.
  const { dom, platform: web } = harness();
  const pending = mount({
    root: dom.root as never,
    platform: { ...web, kind: "tauri" },
    now: () => 1,
    newChatId: () => "c1",
  });

  const panel = emptyPanel(dom);
  assert.ok(panel, "no empty state was painted before boot finished");
  assert.equal(panel.hidden, false, "the chrome was a blank rectangle while booting");
  // The WELCOME, not the guidance: nothing has asked the keychain yet, and
  // guessing "no key" here would accuse a configured user on every launch.
  assert.ok(panel.textContent.includes(en.emptyTranscript), panel.textContent);
  assert.equal(
    panel.textContent.includes(en.emptyNeedsKeyTitle),
    false,
    "a key was declared missing before anything asked the keychain",
  );

  const app = await pending;
  await settle();
  // And once boot has finished and the keychain has answered, it becomes the
  // guidance -- so the seed is a starting state, not a state it gets stuck in.
  assert.ok(emptyWords(dom).includes(en.emptyNeedsKeyTitle), emptyWords(dom));
  await app?.dispose();
});
