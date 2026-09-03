/**
 * Choosing a platform, once, at startup.
 *
 * This is the only file allowed to name both `createTauriShell` and
 * `createWebShell`. Everything above it takes a `ShellPort` and cannot tell
 * which one it got -- which is the whole point of the UI-shell seam, and the
 * property that makes a React Native port a new directory rather than an audit.
 *
 * The probe is SYNCHRONOUS. `ShellPort.insets` has to be readable during the
 * first paint, so "is there a native shell here" cannot be a promise: an async
 * answer would make the first frame guess, paint wrong, and jump -- the single
 * most obvious "this is a web page in a box" tell there is.
 */
import type { ShellPort } from "../../core/src/ports/shell.ts";
import type { StoragePort } from "../../core/src/ports/storage.ts";
import type { SecretsPort } from "../../core/src/ports/secrets.ts";
import type { HttpPort } from "../../core/src/ports/http.ts";
import type { TimePort } from "../../core/src/ports/time.ts";
import { createTauriBridge, type TauriBridge } from "../../adapters/src/tauri/bridge.ts";
import { createTauriShell } from "../../adapters/src/tauri/shell.ts";
import { createWebShell } from "../../adapters/src/web/shell.ts";
import { createWebStorage } from "../../adapters/src/web/storage.ts";
import { createTauriStorage } from "../../adapters/src/tauri/storage.ts";
import { migrateStorage, preparedStorage } from "../../adapters/src/storage/migrate.ts";
import { createWebSecrets } from "../../adapters/src/web/secrets.ts";
import { createWebHttp } from "../../adapters/src/web/http.ts";
import { createWebTime } from "../../adapters/src/web/time.ts";

export interface Platform {
  readonly shell: ShellPort;
  readonly storage: StoragePort;
  readonly secrets: SecretsPort;
  readonly http: HttpPort;
  readonly time: TimePort;
  /** What the app is actually running on, for the About screen and for a
   *  warning the user deserves when secrets are not hardware backed. */
  readonly kind: "tauri" | "web";
}

export interface PlatformDeps {
  /** Injected so a test can force either branch without a Tauri global. */
  readonly isNative?: () => boolean;
  readonly view?: Window;
  /**
   * Where `__TAURI_INTERNALS__` is looked up, forwarded to the bridge.
   *
   * Injected so the NATIVE storage path is exercised in CI rather than only
   * the web one. Without it a test can flip `isNative` and still get a bridge
   * with no host behind it, which is how "the Tauri build silently used
   * localStorage" survived a full suite in the first place.
   */
  readonly scope?: object;
}

/**
 * The StoragePort each platform gets.
 *
 * The per-platform default, in one named function, for the same reason
 * `defaultEngineIdFor` is one: a `? :` buried in the object literal below is a
 * decision no test can name. On a device this is the native file store; in a
 * browser it stays `localStorage`, which is the only store a browser has.
 *
 * The Tauri store is WRAPPED, not replaced: `preparedStorage` runs the
 * one-time copy out of `localStorage` before the first read, so an existing
 * install's conversations move with it instead of appearing to have been
 * deleted by the upgrade. See adapters/src/storage/migrate.ts.
 */
export function storageFor(
  kind: Platform["kind"],
  bridge: TauriBridge,
  view: Window,
): StoragePort {
  const web = createWebStorage(view.localStorage);
  if (kind !== "tauri") return web;

  const native = createTauriStorage({ invoke: bridge.invokeStrict });
  return preparedStorage(native, () => migrateStorage(web, native));
}

export function detectPlatform(deps: PlatformDeps = {}): Platform {
  const bridge = createTauriBridge(deps.scope === undefined ? {} : { scope: deps.scope });
  const native = deps.isNative?.() ?? bridge.isPresent();
  const view = deps.view ?? globalThis.window;

  // Secrets and http are still the web adapters under Tauri. That is a
  // deliberate, temporary state and not an oversight: a keychain SecretsPort,
  // and an HttpPort that sends from Rust (so a request is not subject to the
  // webview's CORS, and a hardware-backed key never crosses into JS) are each
  // their own piece of work. Naming it here means the next author finds the
  // seam rather than assuming it was considered and rejected.
  //
  // STORAGE is no longer on that list. `localStorage` in WKWebView is
  // EVICTABLE under storage pressure -- the user does nothing wrong and their
  // history is gone -- so on a device it is now the native file store in
  // src-tauri/src/store.rs, which writes to the app's data directory with
  // temp-then-rename.
  return {
    shell: native ? createTauriShell({ bridge }) : createWebShell(view),
    storage: storageFor(native ? "tauri" : "web", bridge, view),
    secrets: createWebSecrets(),
    http: createWebHttp(),
    time: createWebTime(),
    kind: native ? "tauri" : "web",
  };
}
