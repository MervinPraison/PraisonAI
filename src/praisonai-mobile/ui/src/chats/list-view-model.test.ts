/**
 * The chat list.
 *
 * The repository goes out of its way to report a corrupt chat rather than skip
 * it. These tests are what stop the UI from throwing that report away again.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { UNTITLED, buildChatList } from "./list-view-model.ts";
import type { ChatSummary } from "../../../core/src/chat/repository.ts";

const NOW = 1_700_000_000_000;
const summary = (id: string, title: string, updated = NOW - 60_000): ChatSummary => ({
  id,
  title,
  updated,
});

test("a chat that could not be read appears in the list rather than vanishing", () => {
  // repository.ts: "One corrupt file must not make a conversation quietly
  // vanish from the list." Rendering only list() throws that report away.
  const view = buildChatList([summary("a", "Working")], ["b"], NOW);
  assert.equal(view.rows.length, 2);
  assert.equal(view.unreadableCount, 1);
  assert.equal(view.rows[0]?.kind, "unreadable", "and it is not buried at the bottom");
});

test("working chats are still listed when nothing is corrupt", () => {
  // The pair: a list that only ever showed problems would show nothing at all
  // on a healthy install.
  const view = buildChatList([summary("a", "Working")], [], NOW);
  assert.equal(view.rows.length, 1);
  assert.equal(view.rows[0]?.kind, "chat");
  assert.equal(view.state, "has-chats");
});

test("an empty list and a list that failed to load are different states", () => {
  // One is a new install. The other is data loss, and rendering them
  // identically means the user is told "no chats yet" about chats they had.
  assert.equal(buildChatList([], [], NOW).state, "none");
  assert.equal(buildChatList([], ["a", "b"], NOW).state, "all-unreadable");
});

test("a blank title renders as Untitled rather than as an empty row", () => {
  // A row with no label looks like a rendering bug and has almost no hit area.
  const view = buildChatList([summary("a", "   ")], [], NOW);
  assert.equal(view.rows[0]?.title, UNTITLED);
});

test("a long title is truncated without breaking an emoji", () => {
  const view = buildChatList([summary("a", "🙂".repeat(200))], [], NOW);
  const title = view.rows[0]?.title ?? "";
  assert.equal(title.includes("�"), false);
  assert.ok(title.length < 200);
});

test("a chat listed as both readable and unreadable is shown only as unreadable", () => {
  // A tap on the stale copy would open a chat whose file cannot be parsed, and
  // the failure would land on the detail screen instead of the list.
  const view = buildChatList([summary("a", "Stale")], ["a"], NOW);
  assert.equal(view.rows.length, 1);
  assert.equal(view.rows[0]?.kind, "unreadable");
});

test("the timestamp column is relative and never negative", () => {
  // A phone whose clock is behind the timestamp it wrote is normal after a
  // sleep, and "in -3 minutes" is a number the user cannot act on.
  const view = buildChatList([summary("a", "x", NOW + 60_000)], [], NOW);
  assert.equal(view.rows[0]?.kind === "chat" && view.rows[0].updatedLabel, "just now");
});
