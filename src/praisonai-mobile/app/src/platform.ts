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
import { createTauriBridge } from "../../adapters/src/tauri/bridge.ts";
import { createTauriShell } from "../../adapters/src/tauri/shell.ts";
import { createWebShell } from "../../adapters/src/web/shell.ts";
import { createWebStorage } from "../../adapters/src/web/storage.ts";
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
}

export function detectPlatform(deps: PlatformDeps = {}): Platform {
  const bridge = createTauriBridge();
  const native = deps.isNative?.() ?? bridge.isPresent();
  const view = deps.view ?? globalThis.window;

  // Storage, secrets and http are still the web adapters under Tauri today.
  // That is a deliberate, temporary state and not an oversight: a Tauri
  // StoragePort over the store plugin, a keychain SecretsPort, and an HttpPort
  // that sends from Rust (so a request is not subject to the webview's CORS,
  // and a hardware-backed key never crosses into JS) are each their own piece
  // of work. Naming it here means the next author finds the seam rather than
  // assuming it was considered and rejected.
  return {
    shell: native ? createTauriShell({ bridge }) : createWebShell(view),
    // localStorage in WKWebView is EVICTABLE under storage pressure, so chat
    // history can disappear without an error. A Tauri store-file StoragePort
    // is the fix; this is the honest interim.
    storage: createWebStorage(view.localStorage),
    secrets: createWebSecrets(),
    http: createWebHttp(),
    time: createWebTime(),
    kind: native ? "tauri" : "web",
  };
}
