/**
 * Accessible names.
 *
 * Driven from real events through core's reducer and the real view model, not
 * from hand-built row literals: the point of the file is that the name reflects
 * the state the wire actually produced, and a literal can assert a state the
 * protocol cannot emit.
 *
 * The guarantee: a tool row's name states its STATUS, so the distinction
 * between "succeeded", "failed" and "never came back" -- which the view model
 * carries as a tone, i.e. a colour -- reaches a user who cannot see colour.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  accessibleName,
  approvalRowName,
  chatRowName,
  routeTitle,
  toolRowName,
} from "./names.ts";
import { en } from "../i18n/strings.ts";
import { UNKNOWN } from "../format.ts";
import { buildChatList } from "../chats/list-view-model.ts";
import { buildTranscript, toolRowsOf, type ToolRowView } from "../transcript/view-model.ts";
import { apply, initialTurn, type TurnState } from "../../../core/src/run/transcript.ts";
import { add, choose, emptyApprovals } from "../../../core/src/run/approvals.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";

const M = "m1";
const start: RunEvent = { type: "start", msgId: M, runId: "r1" };
const run = (...events: readonly RunEvent[]): TurnState =>
  events.reduce<TurnState>(apply, initialTurn);

const call = (callId: string, name: string): RunEvent =>
  ({ type: "tool_call", msgId: M, callId, name, args: { path: "/etc/passwd" } });
const result = (callId: string, name: string, ok: boolean, seconds: number | null): RunEvent =>
  ({ type: "tool_result", msgId: M, callId, name, ok, output: "", seconds });

const toolNamed = (turn: TurnState, callId: string): ToolRowView => {
  const row = toolRowsOf(buildTranscript(turn)).find((r) => r.callId === callId);
  assert.ok(row !== undefined, `no tool row for ${callId}`);
  return row;
};

test("a tool row's name states its status, not just the tool's name", () => {
  // THE BUG. The row paints a name, a coloured dot and a duration; only the
  // name is in the accessibility tree, so the whole outcome is conveyed by hue.
  const turn = run(start, call("c1", "search"), result("c1", "search", false, 1.24));
  const name = toolRowName(en, toolNamed(turn, "c1"));
  assert.notEqual(name, "search", "the bare tool name is what this file exists to replace");
  assert.ok(name.startsWith("Failed"));
  assert.ok(name.includes("search"));
  assert.ok(name.includes("1.2s"));
});

test("a tool that never came back is named differently from one that succeeded", () => {
  // The view model gives `unresolved` its own tone precisely so the two cannot
  // look the same. This is that same rule in words.
  const finished = run(
    start,
    call("c1", "search"),
    result("c1", "search", true, 1),
    { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  );
  const abandoned = run(
    start,
    call("c1", "search"),
    { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  );
  assert.equal(toolNamed(abandoned, "c1").status, "unresolved");
  assert.notEqual(
    toolRowName(en, toolNamed(abandoned, "c1")),
    toolRowName(en, toolNamed(finished, "c1")),
  );
});

test("an unmeasured duration is named in words rather than an em dash", () => {
  // `seconds: null` means the engine never saw the call begin. "—" is read as
  // silence by most screen readers, which sounds exactly like a row that has no
  // duration because it is still running.
  const turn = run(start, call("c1", "search"), result("c1", "search", true, null));
  const row = toolNamed(turn, "c1");
  assert.equal(row.durationKnown, false);
  assert.equal(row.durationLabel, UNKNOWN);
  const name = toolRowName(en, row);
  assert.equal(name.includes(UNKNOWN), false);
  assert.ok(/unknown/i.test(name), name);
});

test("the spoken duration is the printed one, never a second computation", () => {
  // The pair: a name that reformatted the seconds itself could disagree with
  // the row a sighted user is looking at, and the two would describe the same
  // call differently.
  const turn = run(start, call("c1", "search"), result("c1", "search", true, 3725));
  const row = toolNamed(turn, "c1");
  assert.ok(toolRowName(en, row).includes(row.durationLabel));
});

test("an approval row's name carries the decision state", () => {
  // The visual signal for `sending` is three greyed-out buttons, and a disabled
  // button is announced as "dimmed" or skipped entirely -- so without this the
  // row goes silent at the exact moment the user is waiting to hear what
  // happened to their answer.
  const turn = run(
    start,
    call("c1", "rm"),
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "rm", args: {} },
  );
  const table = add(emptyApprovals, { approvalId: "ap1", callId: "c1", name: "rm", args: {} });
  const pendingView = buildTranscript(turn, table);
  const sendingView = buildTranscript(turn, choose(table, "ap1", "allow"));

  const pendingRow = pendingView.rows.find((r) => r.kind === "approval");
  const sendingRow = sendingView.rows.find((r) => r.kind === "approval");
  assert.ok(pendingRow?.kind === "approval" && sendingRow?.kind === "approval");
  assert.ok(approvalRowName(en, pendingRow).includes("rm"));
  assert.notEqual(approvalRowName(en, pendingRow), approvalRowName(en, sendingRow));
  assert.equal(/allowed/i.test(approvalRowName(en, sendingRow)), false);
});

test("a text row has NO accessible name, deliberately", () => {
  // aria-label REPLACES an element's content in the accessibility tree. Putting
  // one on a paragraph of model output makes it one unbrowsable blob: no word,
  // sentence or character navigation. Null means "its own text is its name".
  const turn = run(start, { type: "delta", msgId: M, text: "Hello there." });
  const textRow = buildTranscript(turn).rows.find((r) => r.kind === "text");
  assert.ok(textRow !== undefined);
  assert.equal(accessibleName(en, textRow), null);
});

test("every row that is not prose DOES get a name", () => {
  // The pair: an implementation returning null for everything passes the test
  // above and leaves every tool, error and approval row nameless.
  const turn = run(
    start,
    { type: "delta", msgId: M, text: "Working." },
    call("c1", "search"),
    result("c1", "search", false, 2),
    { type: "error", msgId: M, kind: "transport", message: "socket closed" },
  );
  const rows = buildTranscript(turn).rows;
  const named = rows.filter((row) => row.kind !== "text" && row.kind !== "reasoning");
  assert.ok(named.length >= 2);
  for (const row of named) {
    const name = accessibleName(en, row);
    assert.ok(typeof name === "string" && name.trim() !== "", row.kind);
  }
});

test("a cancelled turn's notice and a dropped-events row are both named", () => {
  const turn = run(
    start,
    { type: "reasoning", msgId: M, text: "thinking" },
    { type: "delta", msgId: "other", text: "wrong turn" },
    { type: "cancelled", msgId: M, runId: "r1" },
  );
  const view = buildTranscript(turn);
  const notice = view.rows.find((r) => r.kind === "notice");
  const dropped = view.rows.find((r) => r.kind === "dropped");
  assert.ok(notice !== undefined && dropped !== undefined);
  assert.equal(accessibleName(en, notice), en.stopped);
  const droppedName = accessibleName(en, dropped);
  assert.ok(droppedName !== null && droppedName.includes("1 event "), droppedName ?? "");
});

test("a chat row is never nameless, and an unreadable one says so", () => {
  // The unreadable rows sort to the top so they are not missed; a screen reader
  // user reaches them first too, and this is what they hear.
  const view = buildChatList(
    [{ id: "a", title: "   ", updated: 0 }],
    ["broken"],
    0,
  );
  const names = view.rows.map((row) => chatRowName(en, row));
  assert.ok(names[0]?.includes("broken"), names[0]);
  assert.equal(names[1], en.untitled);
  for (const name of names) assert.notEqual(name.trim(), "");
});

test("every route has a title, so no screen's heading is blank", () => {
  const titles = [
    routeTitle(en, { name: "chats" }),
    routeTitle(en, { name: "chat", chatId: "x" }),
    routeTitle(en, { name: "settings" }),
    routeTitle(en, { name: "about" }),
  ];
  for (const title of titles) assert.notEqual(title.trim(), "");
  assert.equal(new Set(titles).size, 4);
});
