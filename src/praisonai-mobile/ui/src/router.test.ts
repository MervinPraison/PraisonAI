/**
 * The route stack and the back gesture.
 *
 * The first test is the one this file exists for. It is asserted through the
 * fake shell rather than by calling the router, because the value that matters
 * is the one the OS receives -- and a router that returns the right thing to a
 * handler nobody registered is still an app you cannot leave.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { attachBackGesture, backDecision, createRouter, sameRoute, type Route } from "./router.ts";
import { createFakeShell } from "../../testing/src/fake-shell.ts";

const CHATS: Route = { name: "chats" };
const SETTINGS: Route = { name: "settings" };
const chat = (chatId: string): Route => ({ name: "chat", chatId });

test("at the root the back gesture is refused so the OS can exit the app", () => {
  // THE RULE. On Android, returning true here traps the user inside the app
  // with no way out but force-quitting it -- and every test that pushes a
  // route first passes regardless.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  attachBackGesture(shell, router);

  assert.equal(shell.pressBack(), false, "the OS was denied the gesture at the root");
  assert.deepEqual(router.stack, [CHATS], "and nothing was popped");
});

test("above the root the back gesture is consumed and pops one route", () => {
  // The pair. Returning false unconditionally satisfies the test above and
  // makes every back press exit the app from wherever the user is.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  attachBackGesture(shell, router);
  router.push(chat("c1"));

  assert.equal(shell.pressBack(), true);
  assert.deepEqual(router.current(), CHATS);
  assert.equal(shell.pressBack(), false, "and the root still releases the gesture");
});

test("the back rule is refusable without a shell at all", () => {
  // Exported as a pure function so the rule is checkable in isolation -- and
  // so an empty stack, which should be impossible, still cannot be popped into
  // a negative length.
  assert.equal(backDecision([]).consumed, false);
  assert.equal(backDecision([CHATS]).consumed, false);
  assert.deepEqual(backDecision([CHATS, SETTINGS]), { consumed: true, stack: [CHATS] });
});

test("popping the root changes nothing rather than emptying the stack", () => {
  // An empty stack renders nothing at all, which looks like a crash but leaves
  // no crash report.
  const router = createRouter(CHATS);
  assert.equal(router.pop(), false);
  assert.equal(router.stack.length, 1);
  assert.deepEqual(router.current(), CHATS);
});

test("pushing the route already on top is ignored", () => {
  // A double tap on a chat row otherwise stacks two identical screens, and the
  // user's first back press appears to do nothing at all.
  const router = createRouter(CHATS);
  assert.equal(router.push(chat("c1")), true);
  assert.equal(router.push(chat("c1")), false);
  assert.equal(router.stack.length, 2);
});

test("pushing a different instance of the same screen is not ignored", () => {
  // The pair: comparing by `name` alone would make every chat after the first
  // one unopenable while a chat is already open.
  const router = createRouter(CHATS);
  router.push(chat("c1"));
  assert.equal(router.push(chat("c2")), true);
  assert.deepEqual(router.current(), chat("c2"));
  assert.equal(sameRoute(chat("c1"), chat("c2")), false);
});

test("subscribers see every change and hold a stack that cannot mutate under them", () => {
  // A subscriber that was handed the live array would diff it against itself
  // and conclude nothing changed.
  const router = createRouter(CHATS);
  const seen: (readonly Route[])[] = [];
  const off = router.subscribe((stack) => void seen.push(stack));

  router.push(chat("c1"));
  router.push(SETTINGS);
  router.pop();

  assert.deepEqual(seen.map((s) => s.length), [2, 3, 2]);
  assert.deepEqual(seen[0], [CHATS, chat("c1")], "the first snapshot did not change later");

  off();
  router.push(SETTINGS);
  assert.equal(seen.length, 3, "an unsubscribed listener kept firing");
});

test("detaching the back gesture leaves no listener behind", () => {
  // A leaked handler pops a router belonging to a torn-down view, which reads
  // to the user as the back button doing nothing.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  const detach = attachBackGesture(shell, router);
  assert.equal(shell.listenerCount(), 1);

  detach();
  assert.equal(shell.listenerCount(), 0);
  router.push(SETTINGS);
  assert.equal(shell.pressBack(), false, "a detached router must not consume the gesture");
});

test("attaching declares whether there is anywhere to go back to", () => {
  // The device bug this exists for: on Settings the app HAD consumed the press
  // and popped, but its answer took seconds to cross the native bridge, the
  // watchdog read the silence as "the app does not want it", and Android took
  // the app away. The native side can only be right about a late answer if it
  // was told the stack IN ADVANCE, so the declaration goes out on attach and on
  // every change -- not in reply to a press.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  const detach = attachBackGesture(shell, router);

  assert.equal(shell.canGoBack(), false, "the root has nothing to pop");

  router.push(SETTINGS);
  assert.equal(shell.canGoBack(), true, "Settings is a route back must keep");

  router.pop();
  assert.equal(shell.canGoBack(), false, "back at the root again");

  // Every change, not just the first: a declaration sent once at startup would
  // be right exactly until the user navigated.
  assert.deepEqual(shell.declared, [false, true, false]);
  detach();
});

test("detaching declares that there is nothing to go back to", () => {
  // A torn-down view's router speaks for nothing. A native side left holding
  // `true` would treat every unanswered press as "the app is just slow" and
  // swallow it -- a back button that does nothing, forever.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  const detach = attachBackGesture(shell, router);
  router.push(SETTINGS);
  assert.equal(shell.canGoBack(), true);

  detach();
  assert.equal(shell.canGoBack(), false, "a detached router must declare nothing to pop");

  router.push(chat("c1"));
  assert.equal(shell.canGoBack(), false, "a detached router must stop declaring at all");
});

test("the declaration says the same thing the handler will answer", () => {
  // Two sources of truth for one question is the failure this is written
  // against: a declaration that says "I can go back" while the handler answers
  // false gets the press swallowed, and the opposite exits the app mid-screen.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  attachBackGesture(shell, router);

  for (const route of [SETTINGS, chat("c1"), SETTINGS]) {
    router.push(route);
    assert.equal(shell.canGoBack(), true);
  }
  while (router.stack.length > 1) {
    const declared = shell.canGoBack();
    assert.equal(shell.pressBack(), declared, "the answer contradicted the declaration");
  }
  assert.equal(shell.canGoBack(), false);
  assert.equal(shell.pressBack(), false, "the root must let the OS act");
});

test("the most recently attached handler gets the gesture first", () => {
  // A modal must consume back ahead of the route beneath it, or dismissing it
  // also navigates.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  attachBackGesture(shell, router);

  let modalDismissed = false;
  const closeModal = shell.onBackGesture(() => {
    modalDismissed = true;
    return true;
  });

  router.push(SETTINGS);
  assert.equal(shell.pressBack(), true);
  assert.equal(modalDismissed, true);
  assert.deepEqual(router.current(), SETTINGS, "the route beneath must not have popped too");

  closeModal();
  assert.equal(shell.pressBack(), true);
  assert.deepEqual(router.current(), CHATS);
});

test("popping to root unwinds a deep stack in one step", () => {
  // Deleting the chat being viewed has to leave, and popping once would land
  // on another screen showing the same deleted chat.
  const router = createRouter(CHATS);
  router.push(chat("c1"));
  router.push(SETTINGS);
  router.popToRoot();
  assert.deepEqual(router.stack, [CHATS]);
});

test("replacing swaps the top without deepening the stack", () => {
  // Forking a chat replaces the one on screen; pushing instead would put the
  // pre-fork chat behind it, and back would appear to undo the fork.
  const router = createRouter(CHATS);
  router.push(chat("c1"));
  router.replace(chat("c2"));
  assert.equal(router.stack.length, 2);
  assert.deepEqual(router.current(), chat("c2"));
});

test("the back handler still works when handed to the shell by reference", () => {
  // `shell.onBackGesture(router.handleBack)` is the obvious way to write it. A
  // `this`-bound method throws inside the OS callback, where the exception is
  // swallowed and the gesture just stops working with nothing logged.
  const shell = createFakeShell();
  const router = createRouter(CHATS);
  shell.onBackGesture(router.handleBack);
  router.push(SETTINGS);

  assert.equal(shell.pressBack(), true);
  assert.equal(shell.pressBack(), false);
});
