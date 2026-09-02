/**
 * The entry point's one decision a test can reach.
 *
 * `mount` needs a whole fake SSE transport to drive end to end, so the parts
 * of it that can be wrong are extracted and called directly instead.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { defaultEngineIdFor, stopNotice } from "./main.ts";
import { en } from "../../ui/src/i18n/strings.ts";

test("every platform's first-launch default is the remote engine, for now", () => {
  // Tempting to default a device to the in-process engine -- a phone cannot
  // reach `http://127.0.0.1:8765` and the cleartext localhost address is
  // refused by iOS ATS and Android -- but the in-process engine's module is
  // ABSENT from the shipping webview: build-webview.mjs bundles only
  // `main.ts` into `dist/app.js`, and the engine reaches praisonai-ts through a
  // runtime-computed import left outside that bundle (#4437). So defaulting a
  // device to it would swap the "not answering" warning (which names Settings
  // as the fix) for a first prompt that fails "unavailable in this build" with
  // no recovery -- the very brick registry.ts keeps the engine out of the
  // picker to avoid. Until #4437 ships praisonai-ts inside the webview, remote
  // is the honest default. `Platform["kind"]` also cannot tell desktop Tauri
  // (`cargo tauri dev`) from a phone, so a `kind === "tauri"` default would
  // strand the desktop/dev flow too.
  assert.equal(defaultEngineIdFor("tauri"), ENGINE_REMOTE_HTTP);
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
import { appEngines, mount } from "./main.ts";
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

  const ids = appEngines({
    settings,
    http: createFakeHttp(),
    persistence,
    onIgnored: () => {},
  }).map((c) => c.id);

  assert.ok(ids.includes(ENGINE_PRAISONAI_TS), `only ${ids.join(", ")} on offer`);
  // And the remote engine is still offered and first, so the default keeps
  // working with nothing configured.
  assert.equal(ids[0], ENGINE_REMOTE_HTTP, "the remote engine must stay the default");
});

test("the in-process engine, when its module cannot load, fails RECOVERABLY", async () => {
  // The factory's dynamic import resolves at run time from a computed
  // specifier, and where praisonai-ts is not on disk -- the shipping webview
  // bundles only dist/ (#4437), and this test runs with the same absence -- it
  // rejects. Constructing the engine must still succeed (create() opens no
  // upstream), and the failure must arrive as a single recoverable `error`
  // event through engine.ts's run loop, never as an unhandled rejection that
  // takes down the turn opaquely. That is the named, on-screen failure
  // engines.ts argues for.
  const secrets = createFakeSecrets();
  const store = createSettingsStore(SETTING_DEFS, createFakeStorage(), secrets);
  await store.load();
  const settings: SettingsFacade = facadeFor(store, secrets);
  const persistence = {
    async record() {
      return { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
  };

  const inProcess = appEngines({
    settings,
    http: createFakeHttp(),
    persistence,
    onIgnored: () => {},
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
  const platform: Platform = {
    shell: createFakeShell(PHONE_INSETS),
    storage,
    secrets: createFakeSecrets(),
    http,
    time: nodeTime(),
    kind: "web",
  };
  return { dom, http, storage, platform };
}

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
  assert.equal(props["--inset-top"], `${PHONE_INSETS.top}px`, "the TOP inset must come from the top");
  assert.notEqual(
    props["--inset-top"],
    `${PHONE_INSETS.bottom}px`,
    "reading the top inset from the bottom puts content under the notch",
  );
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
  const screen = dom.find((n) => n.className === "screen");
  assert.ok(screen, "no screen element");
  const props = (screen as unknown as { style: { props: Record<string, string> } }).style.props;

  shell.setInsets({ top: 99, bottom: 12, left: 3, right: 4 });
  await settle(20);
  assert.equal(props["--inset-top"], "99px", "a rotation must reach the layout");
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
  (field as { dispatch(t: string, e: unknown): void }).dispatch("change", {});
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
  (select as { dispatch(t: string, e: unknown): void }).dispatch("change", {});
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
  (field as { dispatch(t: string, e: unknown): void }).dispatch("change", {});
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
