/**
 * A route stack, and the back gesture wired to it.
 *
 * The one rule that matters is stated in core/src/ports/shell.ts and repeated
 * here because it is the whole reason this file is not three lines inside a
 * view: the back callback returns true when the app consumed the gesture and
 * false when it did not, and FALSE AT THE ROOT IS MANDATORY. On Android false
 * is what lets the OS act -- which at the root means leaving the app. A handler
 * that returns true unconditionally traps the user inside a chat app with no
 * way out except force-quitting it, and it does so silently: every test that
 * only ever pushes a route passes.
 *
 * `backDecision` is therefore a pure exported function over the stack, so the
 * rule can be asserted without a shell, and `attachBackGesture` is the thin
 * wiring that a fake shell drives end to end.
 *
 * Everything is immutable-in, immutable-out. The stack is copied on every
 * change so a subscriber can hold the previous one and diff against it, rather
 * than being handed an array that mutated under it.
 */
import type { ShellPort, Unsubscribe } from "../../core/src/ports/shell.ts";

/**
 * Every screen. A union rather than a string, so a route with a missing
 * parameter is a compile error instead of a blank screen.
 *
 * (Not an enum: tsconfig sets `erasableSyntaxOnly`, and an enum emits real
 * JavaScript that type-stripping cannot produce.)
 */
export type Route =
  | { readonly name: "chats" }
  | { readonly name: "chat"; readonly chatId: string }
  | { readonly name: "settings" }
  | { readonly name: "about" };

export interface BackDecision {
  /** What the back handler must return. False lets the OS act. */
  readonly consumed: boolean;
  readonly stack: readonly Route[];
}

/** Same screen showing the same thing? Used to swallow a double tap. */
export function sameRoute(a: Route, b: Route): boolean {
  if (a.name !== b.name) return false;
  if (a.name === "chat" && b.name === "chat") return a.chatId === b.chatId;
  return true;
}

/**
 * The back rule, as a function of the stack alone.
 *
 * A stack of one -- or, defensively, of none -- is the root: not consumed.
 */
export function backDecision(stack: readonly Route[]): BackDecision {
  if (stack.length <= 1) return { consumed: false, stack };
  return { consumed: true, stack: stack.slice(0, -1) };
}

export interface Router {
  readonly stack: readonly Route[];
  current(): Route;
  /** Ignores a push of the route already on top, so a double tap on a chat
   *  does not require two back presses to leave it. */
  push(route: Route): boolean;
  replace(route: Route): void;
  /** Returns false at the root, having changed nothing. */
  pop(): boolean;
  /** Exactly what the OS back handler must return. */
  handleBack(): boolean;
  /** Back to the root, e.g. after deleting the chat being viewed. */
  popToRoot(): void;
  subscribe(cb: (stack: readonly Route[]) => void): Unsubscribe;
}

export function createRouter(root: Route): Router {
  let stack: readonly Route[] = [root];
  const subscribers = new Set<(stack: readonly Route[]) => void>();

  const commit = (next: readonly Route[]): void => {
    stack = next;
    for (const cb of subscribers) cb(stack);
  };

  // Plain closures rather than methods using `this`. A back handler is passed
  // by reference to the shell, and `shell.onBackGesture(router.handleBack)` on
  // a `this`-bound method throws inside an OS callback -- where the exception
  // is swallowed and the gesture simply stops working.
  const current = (): Route =>
    // The stack is never empty -- pop refuses at the root -- but the fallback
    // is here rather than a non-null assertion, because a blank screen with no
    // way back is a worse failure than an extra branch.
    stack[stack.length - 1] ?? root;

  const pop = (): boolean => {
    const decision = backDecision(stack);
    if (!decision.consumed) return false;
    commit(decision.stack);
    return true;
  };

  return {
    get stack() {
      return stack;
    },

    current,

    push(route) {
      if (sameRoute(current(), route)) return false;
      commit([...stack, route]);
      return true;
    },

    replace(route) {
      commit([...stack.slice(0, -1), route]);
    },

    pop,

    handleBack: pop,

    popToRoot() {
      if (stack.length <= 1) return;
      commit([stack[0] ?? root]);
    },

    subscribe(cb) {
      subscribers.add(cb);
      return () => void subscribers.delete(cb);
    },
  };
}

/**
 * Wire the router to the OS gesture.
 *
 * Returns the unsubscribe, and returning it is not a formality: a leaked
 * handler keeps popping a router belonging to a torn-down view on every back
 * press, which reads to the user as the button doing nothing.
 */
export function attachBackGesture(shell: ShellPort, router: Router): Unsubscribe {
  return shell.onBackGesture(() => router.handleBack());
}
