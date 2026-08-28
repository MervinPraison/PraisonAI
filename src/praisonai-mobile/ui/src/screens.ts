/**
 * Which screen a route shows, and what changes when you move between two.
 *
 * The view models have existed for a while and nothing mounted them: the app
 * rendered one hard-coded transcript and the router drove nothing. This is the
 * missing decision layer, and it is pure for the usual reason -- the cases that
 * matter are about what should be KEPT, and a test that can only inspect a DOM
 * cannot distinguish "rebuilt identically" from "left alone".
 *
 * The distinction is not academic. Rebuilding the transcript on every return
 * from settings throws away every row node and, with them, the scroll position
 * -- so a user who scrolls up, opens settings and comes back is dumped at the
 * bottom of a conversation they were reading. That is the single most annoying
 * bug a chat app can have, and it is invisible to a test that only asserts the
 * right rows are present afterwards.
 */
import type { Route } from "./router.ts";

export type ScreenId = "chats" | "chat" | "settings" | "about";

/**
 * Screens whose DOM survives being navigated away from.
 *
 * `chat` is retained because it holds scroll position and a live stream; the
 * others are cheap to rebuild and holding them would keep stale data on screen
 * when the user returns.
 */
export const RETAINED: ReadonlySet<ScreenId> = new Set<ScreenId>(["chat"]);

export function screenFor(route: Route): ScreenId {
  switch (route.name) {
    case "chats":
      return "chats";
    case "chat":
      return "chat";
    case "settings":
      return "settings";
    case "about":
      return "about";
    default: {
      // Exhaustiveness: a new route with no screen would otherwise render
      // nothing at all, which reads as a frozen app rather than a missing case.
      const never: never = route;
      throw new Error(`no screen for route ${JSON.stringify(never)}`);
    }
  }
}

export interface ScreenChange {
  /** The screen to show. */
  readonly show: ScreenId;
  /** Screens to build now because they do not exist yet. */
  readonly mount: readonly ScreenId[];
  /** Screens to destroy. A retained screen is hidden, never destroyed. */
  readonly unmount: readonly ScreenId[];
  /** Screens to keep in the DOM but hide. */
  readonly hide: readonly ScreenId[];
  /** True when nothing at all needs to change. */
  readonly noop: boolean;
}

/**
 * What must happen to move from `from` to `to`.
 *
 * `live` is the set of screens currently in the DOM, which the caller owns --
 * this function stays pure and the caller stays dumb.
 */
export function transition(
  from: Route | null,
  to: Route,
  live: ReadonlySet<ScreenId>,
): ScreenChange {
  const next = screenFor(to);
  const previous = from === null ? null : screenFor(from);

  if (previous === next && live.has(next)) {
    // Same screen, already built. A chat-to-chat move is a CONTENT change, not
    // a screen change -- rebuilding here would drop the transcript on every
    // navigation within the same screen.
    return { show: next, mount: [], unmount: [], hide: [], noop: true };
  }

  const mount = live.has(next) ? [] : [next];
  const hide: ScreenId[] = [];
  const unmount: ScreenId[] = [];

  if (previous !== null && previous !== next) {
    if (RETAINED.has(previous)) hide.push(previous);
    else unmount.push(previous);
  }

  // Anything else still live that is neither the target nor the screen we came
  // from is stale: it was retained earlier and is not being returned to.
  for (const id of live) {
    if (id === next || id === previous) continue;
    if (!RETAINED.has(id)) unmount.push(id);
    else hide.push(id);
  }

  return { show: next, mount, unmount, hide, noop: false };
}
