/**
 * The entry point's one decision a test can reach.
 *
 * `mount` needs a whole fake SSE transport to drive end to end, so the parts
 * of it that can be wrong are extracted and called directly instead.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { stopNotice } from "./main.ts";
import { en } from "../../ui/src/i18n/strings.ts";

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
import { createFakeHttp, sseResponse } from "../../testing/src/fake-http.ts";
import { mount } from "./main.ts";
import type { Platform } from "./platform.ts";

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
