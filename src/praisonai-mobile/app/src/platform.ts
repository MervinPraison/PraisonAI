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
import { createTauriSecrets } from "../../adapters/src/tauri/secrets.ts";
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

/**
 * The SecretsPort each platform gets.
 *
 * The same shape as `storageFor`, and named for the same reason: a `? :` in
 * the object literal below is a decision no test can name. On a device this is
 * the platform keychain -- iOS Keychain, Android Keystore -- through
 * `src-tauri/plugins/secrets`; in a browser it stays a module-scoped Map,
 * because a browser has no keychain and `localStorage` would be strictly
 * worse than memory for a credential (readable by any script on the origin,
 * and copied into the profile backup).
 *
 * NOT wrapped in a migration, unlike `storageFor`. There is nothing to move:
 * the web adapter's Map dies with the process, so no install has a secret
 * anywhere else to bring across. A migration here would be code that can only
 * ever read an empty map -- and, worse, a code path that reads secrets at boot.
 */
export function secretsFor(kind: Platform["kind"], bridge: TauriBridge): SecretsPort {
  if (kind !== "tauri") return createWebSecrets();
  // `invokeStrict`: a rejecting keychain must not arrive as `null`, which is
  // this port's word for "never configured". See adapters/src/tauri/secrets.ts.
  return createTauriSecrets({ invoke: bridge.invokeStrict });
}

export function detectPlatform(deps: PlatformDeps = {}): Platform {
  const bridge = createTauriBridge(deps.scope === undefined ? {} : { scope: deps.scope });
  const native = deps.isNative?.() ?? bridge.isPresent();
  const view = deps.view ?? globalThis.window;

  // HTTP is still the web adapter under Tauri. That is a deliberate,
  // temporary state and not an oversight: an HttpPort that sends from Rust --
  // so a request is not subject to the webview's CORS, and a key never crosses
  // into JS at all -- is its own piece of work. Naming it here means the next
  // author finds the seam rather than assuming it was considered and rejected.
  //
  // STORAGE is no longer on that list. `localStorage` in WKWebView is
  // EVICTABLE under storage pressure -- the user does nothing wrong and their
  // history is gone -- so on a device it is now the native file store in
  // src-tauri/src/store.rs, which writes to the app's data directory with
  // temp-then-rename.
  //
  // SECRETS is no longer on it either, and that one was worse than eviction:
  // `createWebSecrets()` is a module-scoped Map, so on a phone the API key was
  // gone on EVERY launch -- not on a crash, not under pressure, every time --
  // and the settings screen warned that secrets were "stored in app memory on
  // this platform" while being perfectly correct about it. It is now the
  // Keychain/Keystore in src-tauri/plugins/secrets.
  return {
    shell: native ? createTauriShell({ bridge }) : createWebShell(view),
    storage: storageFor(native ? "tauri" : "web", bridge, view),
    secrets: secretsFor(native ? "tauri" : "web", bridge),
    http: createWebHttp(),
    time: createWebTime(),
    kind: native ? "tauri" : "web",
  };
}
