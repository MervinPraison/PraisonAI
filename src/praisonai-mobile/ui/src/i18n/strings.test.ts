/**
 * The English string table.
 *
 * Three guarantees. First, the table is a faithful lift of the literals that
 * are hardcoded at render sites today -- if these assertions hold, moving those
 * call sites onto the table changes no pixel. Second, no string is blank and no
 * parameterised string drops its argument, because a label that silently loses
 * the tool name is worse than one that is missing. Third, the distinctions the
 * rest of the package fought for survive the translation layer: `unresolved`
 * must not read like `ok`, and `sending` must not read like "allowed".
 */
import test from "node:test";
import assert from "node:assert/strict";

import { en, stringKeys } from "./strings.ts";
import { ERROR_KINDS } from "../../../protocol/src/events.ts";
import { UNKNOWN } from "../format.ts";

/** One sample call per parameterised key. The completeness of THIS table is
 *  asserted below, so a new function key cannot be added without a sample. */
const SAMPLES: Readonly<Record<string, () => string>> = {
  bootFailed: () => en.bootFailed("no storage"),
  engineNotReady: () => en.engineNotReady("ECONNREFUSED"),
  settingRejected: () => en.settingRejected("Engine address"),
  settingRejectedExample: () =>
    en.settingRejectedExample("Engine address", "http://192.168.1.10:8765"),
  settingInactive: () => en.settingInactive("Engine", "remote-http"),
  secretStored: () => en.secretStored("OpenAI API key"),
  secretCleared: () => en.secretCleared("OpenAI API key"),
  chatUnreadable: () => en.chatUnreadable("chat-7"),
  chatsAllUnreadable: () => en.chatsAllUnreadable(3),
  chatUpdated: () => en.chatUpdated("Trip plan", "2h ago"),
  deleteChat: () => en.deleteChat("Trip plan"),
  deleteChatConfirm: () => en.deleteChatConfirm("Trip plan"),
  chatDeleted: () => en.chatDeleted("Trip plan"),
  minutesAgo: () => en.minutesAgo(2, "2"),
  hoursAgo: () => en.hoursAgo(2, "2"),
  daysAgo: () => en.daysAgo(2, "2"),
  durationSeconds: () => en.durationSeconds("1.2"),
  durationMinutesSeconds: () => en.durationMinutesSeconds("1", "02"),
  durationHoursMinutes: () => en.durationHoursMinutes("1", "02"),
  draftingTool: () => en.draftingTool("bash"),
  droppedEvents: () => en.droppedEvents(2, ["wrong_msg_id"]),
    droppedReason: () => en.droppedReason("wrong_msg_id"),
  toolStatus: () => en.toolStatus("unresolved"),
  toolRowName: () => en.toolRowName("failed", "search", "1.2s"),
  approvalQuestion: () => en.approvalQuestion("bash"),
  approvalChoice: () => en.approvalChoice("always"),
  approvalState: () => en.approvalState("sending"),
  approvalRowName: () => en.approvalRowName("bash", "pending"),
  approvalFailed: () => en.approvalFailed("timeout"),
  errorTitle: () => en.errorTitle("auth"),
  errorRowName: () => en.errorRowName("auth", "bad key"),
  recoveryLabel: () => en.recoveryLabel("retry"),
  usageChars: () => en.usageChars("1.5k"),
  usageElapsed: () => en.usageElapsed("12s"),
  usageTimeToFirstToken: () => en.usageTimeToFirstToken("0.4s"),
  announceToolStarted: () => en.announceToolStarted("search"),
  announceToolFinished: () => en.announceToolFinished("ok", "search", "1.2s"),
  announceApproval: () => en.announceApproval("bash"),
  announceError: () => en.announceError("transport", "socket closed"),
  announceDropped: () => en.announceDropped(2),
  announceScreen: () => en.announceScreen("Chats"),
};

test("the table reproduces the literals that are hardcoded at render sites today", () => {
  // The audit list. Every one of these is currently an English literal inside
  // a view model or a DOM helper; if they match here, moving those call sites
  // onto the table is a lift and not a rewrite.
  assert.equal(en.stopped, "Stopped"); // ui/src/transcript/view-model.ts
  assert.equal(en.untitled, "Untitled"); // ui/src/chats/list-view-model.ts
  assert.equal(en.chatUnreadable("abc"), "Could not be read: abc"); // same file
  assert.equal(en.approvalQuestion("bash"), "Allow bash?"); // app/src/dom.ts
  assert.equal(en.approvalChoice("allow"), "Allow"); // app/src/dom.ts
  assert.equal(en.approvalChoice("always"), "Always allow"); // app/src/dom.ts
  assert.equal(en.approvalChoice("deny"), "Deny"); // app/src/dom.ts
  assert.equal(en.unknownValue, UNKNOWN); // ui/src/format.ts
  assert.equal(en.justNow, "just now"); // ui/src/format.ts
  // Landed in app/src/main.ts as a second, app-local `AppStrings` table while
  // this one was being written. Kept identical here so consolidating the two is
  // a rewire and not a retranslation.
  assert.equal(en.appName, "PraisonAI");
  assert.equal(en.newChat, "New chat");
  assert.equal(en.actionSend, "Send");
  assert.equal(en.actionStop, "Stop");
  assert.equal(en.routeSettings, "Settings");
  assert.equal(en.chatsEmpty, "No conversations yet.");
  assert.equal(en.emptyTranscript, "Ask something to begin.");
  // The empty chat screen's own copy. Pinned like the rest: these are the two
  // sentences a new user reads before anything else in the product, and they
  // were reviewed as copy rather than typed into a render site.
  assert.equal(en.emptyNeedsKeyTitle, "Add an API key to start");
  assert.equal(
    en.emptyNeedsKeyBody,
    "PraisonAI answers using your own OpenAI account. Paste a key in Settings and this chat is ready.",
  );
  assert.equal(
    en.emptyAbout,
    "PraisonAI answers questions, explains things, and works through tasks with you.",
  );
  assert.equal(en.crashed, "Something went wrong. Your conversations are saved.");
  assert.equal(en.bootFailed("no storage"), "PraisonAI could not start: no storage");
});

test("no string is blank and no parameterised string drops its argument", () => {
  // A blank label is a button with no name; a label that loses the tool name
  // asks "Allow?" about nothing at all. Both look like a rendering bug.
  for (const key of stringKeys()) {
    const value = (en as unknown as Record<string, unknown>)[key];
    if (typeof value === "string") {
      assert.notEqual(value.trim(), "", key);
      continue;
    }
    assert.equal(typeof value, "function", key);
    const sample = SAMPLES[key];
    assert.ok(sample !== undefined, `no sample call for parameterised key "${key}"`);
    assert.notEqual(sample().trim(), "", key);
  }
  assert.ok(en.approvalQuestion("bash").includes("bash"));
  assert.ok(en.chatUnreadable("chat-7").includes("chat-7"));
  assert.ok(en.errorRowName("auth", "bad key").includes("bad key"));
  assert.ok(en.droppedEvents(2, ["wrong_msg_id"]).includes("wrong_msg_id"));
  // The refusal has to NAME the setting: the field it belongs to may already
  // be off screen, and "that value was refused" alone says which of nothing.
  assert.ok(en.settingRejected("Engine address").includes("Engine address"));
});

test("every sample corresponds to a key that still exists", () => {
  // The pair to the test above: a stale sample would let a deleted key keep
  // "passing" and hide the fact that the completeness check no longer covers
  // anything.
  const keys = new Set<string>(stringKeys());
  for (const key of Object.keys(SAMPLES)) assert.ok(keys.has(key), `stale sample "${key}"`);
});

test("a tool that never came back does not read like one that worked", () => {
  // THE RULE the whole transcript layer is built on. The view model gives
  // `unresolved` its own tone -- a COLOUR -- and this is the same distinction
  // made in words, for a user who cannot see colour.
  assert.notEqual(en.toolStatus("unresolved"), en.toolStatus("ok"));
  assert.notEqual(en.toolStatus("failed"), en.toolStatus("ok"));
  assert.equal(en.toolStatus("unresolved").toLowerCase().includes("done"), false);
  const names = new Set(["running", "ok", "failed", "unresolved"].map((s) =>
    en.toolStatus(s as "ok")));
  assert.equal(names.size, 4, "two statuses share a label");
});

test("a decision in flight does not read as a decision delivered", () => {
  // The desktop said "Allowed" the instant the button was tapped, then sat
  // blocked for 300 seconds on an answer that never arrived.
  assert.notEqual(en.approvalState("sending"), en.approvalState("sent"));
  assert.equal(en.approvalState("sending").toLowerCase().includes("allowed"), false);
  const states = new Set(["pending", "sending", "sent", "failed"].map((s) =>
    en.approvalState(s as "sent")));
  assert.equal(states.size, 4);
});

test("every error kind has its own title, chosen by kind and not by message", () => {
  // recoveryFor() picks the ACTION from `kind`; the title has to come from the
  // same place, or the two disagree about what went wrong.
  const titles = ERROR_KINDS.map((kind) => en.errorTitle(kind));
  assert.equal(new Set(titles).size, ERROR_KINDS.length);
  for (const title of titles) assert.notEqual(title.trim(), "");
  // The provider's prose is appended, never parsed.
  assert.ok(en.errorRowName("internal", "socket hung up").endsWith("socket hung up"));
});

test("counts use CLDR plurals rather than a trailing s", () => {
  assert.equal(en.droppedEvents(1, []), "1 event could not be read");
  assert.equal(en.droppedEvents(2, []), "2 events could not be read");
  assert.equal(en.droppedEvents(0, []), "0 events could not be read");
  assert.equal(en.minutesAgo(1, "1"), "1 minute ago");
});

test("the tool row name carries status, name and duration -- in that order", () => {
  // Status first: a screen reader user arrowing through forty rows hears the
  // first word of each, and needs to know which one broke without waiting out
  // the whole row.
  const name = en.toolRowName("failed", "search", "1.2s");
  assert.ok(name.startsWith("Failed"));
  assert.ok(name.includes("search"));
  assert.ok(name.includes("1.2s"));
});

test("an unmeasured duration is spoken as words, not as an em dash", () => {
  // "—" is read by most screen readers as nothing, so the row would end in a
  // silence indistinguishable from a tool that is still running.
  const unmeasured = en.toolRowName("ok", "search", null);
  assert.equal(unmeasured.includes(UNKNOWN), false);
  assert.ok(/unknown/i.test(unmeasured), unmeasured);
});

// ---- gap 7: a dropped event says what happened ------------------------------

test("a dropped reason reads as a sentence, not a machine tag", () => {
  // A user seeing `wrong_msg_id` learns nothing at all. This is the whole gap.
  assert.match(en.droppedReason("wrong_msg_id"), /different message/);
  assert.match(en.droppedReason("unparseable_json"), /not valid JSON/);
});

test("the machine tag is KEPT alongside the sentence", () => {
  // Translating the tag away would make the one searchable string in the
  // message unsearchable for whoever the user reports it to.
  const text = en.droppedEvents(1, ["wrong_msg_id"]);
  assert.match(text, /\[wrong_msg_id\]/, "the tag must survive");
  assert.match(text, /different message/, "and so must the explanation");
});

test("an unknown reason passes through rather than becoming 'unknown'", () => {
  // A newer engine can invent one, and the tag is still the thing worth
  // reporting -- replacing it with a generic phrase destroys the only
  // information in the message.
  assert.equal(en.droppedReason("some_future_reason"), "some_future_reason");
});

test("no reasons means no trailing punctuation", () => {
  // The pair for the formatting: a dangling ":" reads as a truncated message.
  const text = en.droppedEvents(2, []);
  assert.ok(!text.includes(":"), text);
  assert.ok(!text.includes("["), text);
});

test("every reason the decoder can produce has a sentence", () => {
  // The exhaustiveness that matters: a reason with no words falls back to its
  // tag, which is safe but is the gap reappearing one enum member at a time.
  const REASONS = [
    "unparseable_json", "not_an_object", "missing_type", "unknown_event",
    "missing_msg_id", "missing_required_field", "empty_text",
    "before_start", "wrong_msg_id", "after_terminal",
  ];
  for (const reason of REASONS) {
    assert.notEqual(en.droppedReason(reason), reason, `${reason} has no sentence`);
  }
});

test("the key guidance says what to do, and names where", () => {
  // The two facts it has to carry. Without the first it is a diagnosis; without
  // the second the user is left hunting for the screen that takes a key -- and
  // "Settings" is the word on the button they will be looking for once they get
  // there. Asserted on the SENSE rather than the exact sentence so the copy can
  // be reworded without the guarantee going quiet.
  assert.match(en.emptyNeedsKeyTitle, /key/i);
  assert.match(en.emptyNeedsKeyBody, /settings/i);
  // And it must not be the raw provider sentence it replaces.
  assert.equal(en.emptyNeedsKeyBody.includes("OPENAI_API_KEY"), false);
});

test("an empty chat with a key set is not told to get a key", () => {
  // The pair. A welcome that mentioned a key would put the app's one blocking
  // requirement in front of a user who has already met it.
  assert.equal(/api key/i.test(`${en.emptyTranscript} ${en.emptyAbout}`), false);
  assert.notEqual(en.emptyAbout.trim(), en.emptyNeedsKeyBody.trim());
});
