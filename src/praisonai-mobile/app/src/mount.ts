/**
 * Putting screens on the page. The thin half.
 *
 * Every decision — which screen a route shows, what to keep, what to destroy —
 * is in `ui/src/screens.ts` and is tested without a DOM. What is left here is
 * creating an element, showing one, and removing another.
 *
 * `hidden` rather than removal is the whole point for a retained screen: the
 * nodes stay, so the transcript keeps its scroll position and its streaming
 * state across a trip to settings and back.
 */
import type { ScreenChange, ScreenId } from "../../ui/src/screens.ts";

export interface ScreenHost {
  /** The element every screen is appended to. */
  readonly root: HTMLElement;
  /** Builds a screen's element. Called once per mount. */
  readonly build: (id: ScreenId) => HTMLElement;
}

export interface MountedScreens {
  readonly nodes: Map<ScreenId, HTMLElement>;
  /** Which ids are currently in the DOM — the input `transition()` needs. */
  live(): ReadonlySet<ScreenId>;
  apply(change: ScreenChange): void;
}

export function createScreens(host: ScreenHost): MountedScreens {
  const nodes = new Map<ScreenId, HTMLElement>();

  return {
    nodes,
    live: () => new Set(nodes.keys()),

    apply(change) {
      // Order matters, and this order is deliberate: mount before hiding, so
      // there is never a frame with nothing on screen. Doing it the other way
      // produces a visible flash on every navigation.
      for (const id of change.mount) {
        if (nodes.has(id)) continue;
        const el = host.build(id);
        el.dataset["screen"] = id;
        nodes.set(id, el);
        host.root.append(el);
      }

      for (const id of change.unmount) {
        nodes.get(id)?.remove();
        nodes.delete(id);
      }

      // `hidden` keeps the node and its scroll position; it also removes the
      // element from the accessibility tree, so a screen reader does not walk
      // an off-screen transcript.
      for (const id of change.hide) {
        const el = nodes.get(id);
        if (el !== undefined) el.hidden = true;
      }

      const shown = nodes.get(change.show);
      if (shown !== undefined) shown.hidden = false;
    },
  };
}
