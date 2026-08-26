/**
 * Every call into Tauri, in one file.
 *
 * boundaries.json grants "@tauri-apps/api" to this path and to nothing else, so
 * the React Native port is "write a second shell.ts" rather than "grep the tree
 * for native calls and hope". Everything above this file sees narrow, typed
 * functions that resolve to a documented value instead of throwing.
 *
 * Three concrete failures this shape prevents:
 *
 *  1. A module-scope `import { invoke } from "@tauri-apps/api/core"` takes the
 *     WHOLE BUNDLE DOWN at import time in a plain browser and under node:test,
 *     before a line of app code runs. That is strictly worse than a missing
 *     feature: there is no screen left to show an error on. Every reach for
 *     Tauri here is lazy and inside a function.
 *  2. A native plugin that is simply not installed (haptics on desktop, share
 *     on a browser) rejects its invoke. Left unhandled that is an unhandled
 *     rejection on a haptic tap. Each function reports `false` instead.
 *  3. Tauri's own event registration is ASYNC while ShellPort's `on*` must
 *     return a synchronous Unsubscribe. That race is resolved once, in
 *     shell.ts, against the promise this file returns -- not re-derived at
 *     four call sites, three of which would get it wrong.
 *
 * Why the injected global comes FIRST, before the npm package: Tauri 2 puts
 * `__TAURI_INTERNALS__` on the webview's window, and `@tauri-apps/api` is a
 * thin wrapper over exactly that. Preferring the global means the adapter works
 * in a bundle that never resolved the package, which is the difference between
 * "no haptics" and "no haptics and no idea why".
 */
import type { HapticKind, SharePayload, Unsubscribe } from "../../../core/src/ports/shell.ts";

// ---------------------------------------------------------------------------
// the shapes we actually use, declared locally
// ---------------------------------------------------------------------------

/**
 * The slice of `window.__TAURI_INTERNALS__` this adapter touches.
 *
 * Declared here rather than imported because @tauri-apps/api is not in
 * node_modules -- and must not need to be for `npm test` to run. Narrow on
 * purpose: two functions is the entire native surface, and anything wider
 * would be a second place to keep in sync with a package we cannot typecheck
 * against.
 */
interface TauriInternals {
  invoke(command: string, args?: Record<string, unknown>): Promise<unknown>;
  /** Registers a JS callback and returns the numeric id Rust calls back with. */
  transformCallback(callback: (payload: unknown) => void, once?: boolean): number;
}

/** The one export we use from "@tauri-apps/api/event", when the package exists. */
interface TauriEventModule {
  listen(event: string, handler: (message: unknown) => void): Promise<() => void>;
}

/** Loads an npm module by specifier. Injectable so the absent path is testable. */
export type ModuleLoader = (specifier: string) => Promise<unknown>;

/**
 * A VARIABLE specifier, deliberately.
 *
 * `import("@tauri-apps/api/event")` with a literal is a `tsc` error (TS2307)
 * while the package is absent, and `npm run typecheck` is a gate this file has
 * to pass. The alternative -- checking in an ambient `declare module` for a
 * package we do not have -- is worse: it would silently shadow the REAL types
 * the day the package is installed, and nobody would notice.
 *
 * The cost is that tools/depgraph.mjs cannot see this specifier (esbuild only
 * reports statically analysable imports), so the boundary rule protects this
 * file by forbidding the specifier everywhere else rather than by observing it
 * here. That is why the global path below is the primary one and this is the
 * fallback: correctness must not depend on an import the bundler cannot follow.
 */
const loadModuleBySpecifier: ModuleLoader = (specifier) => import(specifier);

const EVENT_MODULE = "@tauri-apps/api/event";

// ---------------------------------------------------------------------------
// the port-facing bridge
// ---------------------------------------------------------------------------

export interface TauriBridge {
  /**
   * Synchronous on purpose. `ShellPort.insets` has to be readable during the
   * first paint, so the decision "is there a native shell here" cannot be a
   * promise either -- an async probe would make the first frame guess.
   */
  isPresent(): boolean;

  /** Resolves to `null` when there is no Tauri and when the command rejects.
   *  A rejecting invoke is a missing plugin, not a programming error. */
  invoke(command: string, args?: Record<string, unknown>): Promise<unknown>;

  /**
   * Resolves to an Unsubscribe -- a no-op one when there is nothing to listen
   * to. Callers therefore never branch on presence, which is what stops
   * "if (tauri)" from spreading back above this file.
   */
  listen(event: string, handler: (payload: unknown) => void): Promise<Unsubscribe>;

  /** `false` means nothing handled it; the caller decides whether that matters. */
  openExternal(url: string): Promise<boolean>;
  haptic(kind: HapticKind): Promise<boolean>;
  share(payload: SharePayload): Promise<boolean>;
}

export interface TauriBridgeDeps {
  /** Where `__TAURI_INTERNALS__` is looked up. Defaults to globalThis; a test
   *  injects a stand-in so the PRESENT path is exercised, not just the absent
   *  one. An adapter whose happy path never runs in CI is an untested adapter. */
  readonly scope?: object;
  /** Defaults to a lazy dynamic import. A test injects a rejecting loader to
   *  pin the "package not installed" behaviour. */
  readonly loadModule?: ModuleLoader;
}

// ---------------------------------------------------------------------------
// unknown -> narrow, without `any`
// ---------------------------------------------------------------------------

/** `__TAURI_INTERNALS__`, or null when this is a plain browser or node:test. */
function readInternals(scope: object): TauriInternals | null {
  const candidate = (scope as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  if (typeof candidate !== "object" || candidate === null) return null;
  const { invoke, transformCallback } = candidate as {
    invoke?: unknown;
    transformCallback?: unknown;
  };
  // Both, not either: a half-present global is a Tauri version we do not speak,
  // and treating it as present would fail every call instead of degrading.
  if (typeof invoke !== "function" || typeof transformCallback !== "function") return null;
  return candidate as TauriInternals;
}

/** Tauri delivers `{ event, id, payload }`; the app only ever wants `payload`. */
function payloadOf(message: unknown): unknown {
  if (typeof message === "object" && message !== null && "payload" in message) {
    return (message as { payload: unknown }).payload;
  }
  return message;
}

const NOOP_UNSUBSCRIBE: Unsubscribe = () => {};

/**
 * Haptics, as the plugin's own JS wrapper would invoke them.
 *
 * A Record keyed by HapticKind rather than a switch, so adding a kind to the
 * port is a type error here instead of a silent fall-through to "no buzz".
 */
const HAPTIC_COMMANDS: Record<HapticKind, { command: string; args: Record<string, unknown> }> = {
  selection: { command: "plugin:haptics|selection_feedback", args: {} },
  impact: { command: "plugin:haptics|impact_feedback", args: { style: "medium" } },
  success: { command: "plugin:haptics|notification_feedback", args: { type: "success" } },
  warning: { command: "plugin:haptics|notification_feedback", args: { type: "warning" } },
  error: { command: "plugin:haptics|notification_feedback", args: { type: "error" } },
};

/** `navigator.share` when the browser has it, else null. Guarded rather than
 *  assumed: node 22 defines `navigator` but not `navigator.share`, so a bare
 *  feature check on `navigator` alone would throw under node:test. */
function webShare(scope: object): ((data: Record<string, string>) => Promise<unknown>) | null {
  const nav = (scope as { navigator?: { share?: unknown } }).navigator;
  if (typeof nav !== "object" || nav === null) return null;
  const share = nav.share;
  if (typeof share !== "function") return null;
  const call = share as (this: unknown, data: Record<string, string>) => unknown;
  return (data) => Promise.resolve(call.call(nav, data));
}

/** `window.open` when there is one. Same guard, same reason. */
function webOpen(scope: object): ((url: string) => void) | null {
  const open = (scope as { open?: unknown }).open;
  if (typeof open !== "function") return null;
  const call = open as (this: unknown, url: string, target: string, features: string) => unknown;
  return (url) => void call.call(scope, url, "_blank", "noopener,noreferrer");
}

/** Only the fields that were actually supplied, because a share sheet that
 *  receives `title: undefined` renders the string "undefined" on some OSes. */
function shareArgs(payload: SharePayload): Record<string, string> {
  const args: Record<string, string> = { text: payload.text };
  if (payload.title !== undefined) args["title"] = payload.title;
  if (payload.url !== undefined) args["url"] = payload.url;
  return args;
}

// ---------------------------------------------------------------------------

export function createTauriBridge(deps: TauriBridgeDeps = {}): TauriBridge {
  const scope: object = deps.scope ?? globalThis;
  const loadModule = deps.loadModule ?? loadModuleBySpecifier;

  /** Resolved once. The lookup is cheap but the ANSWER must not change
   *  mid-session: a shell that decides it is native for insets and web for
   *  haptics is two shells wearing one coat. */
  const internals = readInternals(scope);

  /** The event module, loaded at most once and never retried. A retry per
   *  subscription would issue one failing dynamic import on every rotation. */
  let eventModule: Promise<TauriEventModule | null> | null = null;

  const loadEventModule = (): Promise<TauriEventModule | null> => {
    eventModule ??= loadModule(EVENT_MODULE).then(
      (mod) => {
        const listen = (mod as { listen?: unknown }).listen;
        return typeof listen === "function" ? (mod as TauriEventModule) : null;
      },
      // Not installed, or not resolvable in this bundle. Both are "no events",
      // and neither is worth an unhandled rejection.
      () => null,
    );
    return eventModule;
  };

  const invoke = async (command: string, args?: Record<string, unknown>): Promise<unknown> => {
    if (internals === null) return null;
    try {
      return await internals.invoke(command, args ?? {});
    } catch {
      // A rejected invoke is an absent plugin or a denied permission. The
      // caller gets `null` and decides; nobody gets a crash on a button tap.
      return null;
    }
  };

  return {
    isPresent: () => internals !== null,

    invoke,

    async listen(event, handler) {
      if (internals !== null) {
        try {
          const callbackId = internals.transformCallback((message) => handler(payloadOf(message)));
          const eventId = await internals.invoke("plugin:event|listen", {
            event,
            target: { kind: "Any" },
            handler: callbackId,
          });
          if (typeof eventId !== "number") return NOOP_UNSUBSCRIBE;
          return () => {
            // Fire-and-forget: an unsubscribe that returned a promise would
            // make every teardown path async, and React cleanup is not.
            void invoke("plugin:event|unlisten", { event, eventId });
          };
        } catch {
          return NOOP_UNSUBSCRIBE;
        }
      }

      const mod = await loadEventModule();
      if (mod === null) return NOOP_UNSUBSCRIBE;
      try {
        const unlisten = await mod.listen(event, (message) => handler(payloadOf(message)));
        return () => void unlisten();
      } catch {
        return NOOP_UNSUBSCRIBE;
      }
    },

    async openExternal(url) {
      if (internals !== null) {
        try {
          await internals.invoke("plugin:opener|open_url", { url });
          return true;
        } catch {
          // The opener plugin is not installed in this build. Fall through to
          // the webview's own opener rather than reporting failure -- a link
          // that does nothing is the bug being avoided here.
        }
      }
      const open = webOpen(scope);
      if (open === null) return false;
      open(url);
      return true;
    },

    async haptic(kind) {
      if (internals === null) return false;
      const { command, args } = HAPTIC_COMMANDS[kind];
      try {
        // NOT routed through `invoke`, because `invoke` swallows the rejection
        // and this is the one caller that needs to know: desktop has no
        // haptics plugin, and "buzzed" vs "silently did nothing" is the whole
        // return value.
        await internals.invoke(command, args);
        return true;
      } catch {
        return false;
      }
    },

    async share(payload) {
      if (internals !== null) {
        try {
          await internals.invoke("plugin:share|share", shareArgs(payload));
          return true;
        } catch {
          // No share plugin in this build; try the webview's own sheet.
        }
      }
      const share = webShare(scope);
      if (share === null) return false;
      try {
        await share(shareArgs(payload));
        return true;
      } catch {
        // The user dismissing the sheet rejects with AbortError. Dismissing is
        // not a failure, and must not surface as one.
        return false;
      }
    },
  };
}
