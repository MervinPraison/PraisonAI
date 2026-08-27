/**
 * The approval table and the prompt queue.
 *
 * Both are small state machines, and both exist because the desktop got them
 * wrong first. The tests are named for the defect, not the function.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  acknowledge,
  add,
  choose,
  emptyApprovals,
  find,
  isActionable,
  outstanding,
  reject,
  type ApprovalTable,
} from "./approvals.ts";
import {
  clear,
  depth,
  emptyQueue,
  enqueue,
  markBusy,
  markIdle,
  next,
  remove,
} from "./queue.ts";

const two = (): ApprovalTable =>
  add(
    add(emptyApprovals, { approvalId: "ap1", callId: "c1", name: "rm", args: { path: "/" } }),
    { approvalId: "ap2", callId: "c2", name: "curl", args: { url: "http://x" } },
  );

// ---- approvals -----------------------------------------------------------

test("a decision is routed by approvalId and never to the first pending row", () => {
  // server.py:342 -- routing by position "silently authorises the wrong command"
  // the moment two are outstanding.
  const table = choose(two(), "ap2", "allow");
  assert.equal(find(table, "ap1")?.state.status, "pending", "the first must be untouched");
  assert.equal(find(table, "ap2")?.state.status, "sending");
});

test("two outstanding approvals resolve independently", () => {
  let table = two();
  table = acknowledge(choose(table, "ap1", "deny"), "ap1");
  table = choose(table, "ap2", "allow");

  assert.equal(find(table, "ap1")?.state.status, "sent");
  assert.equal(find(table, "ap2")?.state.status, "sending");
});

test("a decision is sending until the engine acknowledges it", () => {
  // The desktop announced "Allowed" optimistically, and a decision that never
  // arrived left the run blocked for 300 seconds while the UI looked fine.
  const chosen = choose(two(), "ap1", "allow");
  assert.equal(chosen.entries[0]?.state.status, "sending", "must not claim delivery yet");

  const done = acknowledge(chosen, "ap1");
  assert.equal(done.entries[0]?.state.status, "sent");
});

test("a rejected decision becomes actionable again rather than dead-ending", () => {
  // The run is STILL blocked on this prompt. A dead end means the user waits
  // out a timeout with no way to intervene.
  const failed = reject(choose(two(), "ap1", "allow"), "ap1", "network");
  const entry = find(failed, "ap1");
  assert.equal(entry?.state.status, "failed");
  assert.equal(isActionable(entry!), true, "the user must be able to retry");
});

test("a retry after a failure is accepted", () => {
  let table = reject(choose(two(), "ap1", "allow"), "ap1", "network");
  table = choose(table, "ap1", "allow");
  assert.equal(find(table, "ap1")?.state.status, "sending");
});

test("a double tap cannot send two decisions for one approval", () => {
  const once = choose(two(), "ap1", "allow");
  const twice = choose(once, "ap1", "deny");
  assert.ok(Object.is(once, twice), "the second tap must be a no-op");

  // The first choice must survive, not the second: a stray tap on Deny after
  // Allow was already sending must not quietly change what was authorised.
  const entry = find(twice, "ap1");
  assert.equal(entry?.state.status, "sending");
  assert.equal(entry?.state.status === "sending" ? entry.state.choice : null, "allow");
});

test("a decision on an already-sent approval is refused", () => {
  const sent = acknowledge(choose(two(), "ap1", "allow"), "ap1");
  assert.ok(Object.is(sent, choose(sent, "ap1", "deny")));
});

test("acknowledging an approval nobody chose is a no-op", () => {
  const table = two();
  assert.ok(Object.is(table, acknowledge(table, "ap1")), "cannot deliver a decision never made");
});

test("a repeated approval_request for the same id does not create a second prompt", () => {
  // The engine repeating itself is not a second request. Two prompts for one
  // tool call is a UI that asks the same question twice and accepts one answer.
  const table = two();
  const again = add(table, { approvalId: "ap1", callId: "c1", name: "rm", args: {} });
  assert.equal(again.entries.length, 2);
  assert.ok(Object.is(table, again));
});

test("a sent approval no longer blocks the run but a failed one does", () => {
  let table = acknowledge(choose(two(), "ap1", "allow"), "ap1");
  table = reject(choose(table, "ap2", "allow"), "ap2", "offline");

  const blocking = outstanding(table).map((e) => e.approvalId);
  assert.deepEqual(blocking, ["ap2"]);
});

// ---- queue ---------------------------------------------------------------

test("a queued prompt cannot start while a turn is in flight", () => {
  // The invariant. `next` returns null rather than handing the prompt over and
  // trusting the caller to check -- otherwise the rule lives at every call site.
  const queue = markBusy(enqueue(emptyQueue, { id: "p1", text: "hello", attachments: [] }));
  assert.equal(next(queue), null);
});

test("a prompt is released once the previous turn is persisted", () => {
  const queued = enqueue(emptyQueue, { id: "p1", text: "hello", attachments: [] });
  const taken = next(markIdle(markBusy(queued)));
  assert.equal(taken?.prompt.id, "p1");
  assert.equal(taken?.queue.busy, true, "taking a prompt starts a turn");
  assert.equal(depth(taken!.queue), 0);
});

test("prompts are released in the order they were sent", () => {
  // Reordering silently answers the user's questions in a sequence they did
  // not ask for.
  let queue = emptyQueue;
  for (const id of ["a", "b", "c"]) {
    queue = enqueue(queue, { id, text: id, attachments: [] });
  }
  const order: string[] = [];
  for (let i = 0; i < 3; i++) {
    const taken = next(queue);
    order.push(taken!.prompt.id);
    queue = markIdle(taken!.queue);
  }
  assert.deepEqual(order, ["a", "b", "c"]);
});

test("an identical prompt sent twice is queued twice", () => {
  // Asking the same thing again is legitimate. Swallowing the second is worse
  // than answering it.
  let queue = enqueue(emptyQueue, { id: "p1", text: "why?", attachments: [] });
  queue = enqueue(queue, { id: "p2", text: "why?", attachments: [] });
  assert.equal(depth(queue), 2);
});

test("a queued prompt can be withdrawn from the middle", () => {
  let queue = emptyQueue;
  for (const id of ["a", "b", "c"]) {
    queue = enqueue(queue, { id, text: id, attachments: [] });
  }
  queue = remove(queue, "b");
  assert.deepEqual(queue.items.map((p) => p.id), ["a", "c"]);
});

test("an empty queue yields nothing even when idle", () => {
  assert.equal(next(emptyQueue), null);
});

test("clearing the queue does not release the in-flight turn", () => {
  // Clearing is "forget what I queued", not "stop what is running". Conflating
  // them would make a Clear button silently abandon the answer on screen.
  const queue = clear(markBusy(enqueue(emptyQueue, { id: "p1", text: "x", attachments: [] })));
  assert.equal(depth(queue), 0);
  assert.equal(queue.busy, true);
});
