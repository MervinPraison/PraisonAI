/**
 * The UI-shell seam.
 *
 * Tauri 2 today, React Native later. Nothing in core/ or ui/ may import a Tauri
 * API; only adapters/src/tauri may, and inside it only bridge.ts touches
 * @tauri-apps directly. tools/depgraph.mjs enforces both mechanically, so the
 * React Native port is one directory rather than an audit.
 *
 * These are precisely the capabilities that differ between the two shells and
 * that a phone needs but a desktop window does not. Note that none of this
 * could be copied from the desktop UI even if the seam did not exist: that file
 * contains exactly one @media query and it is prefers-color-scheme, so there is
 * no responsive layout, no inset handling and no keyboard awareness to port.
 */

export type ShellKind = "tauri" | "react-native" | "web" | "fake";

export type Unsubscribe = () => void;

/**
 * Finite, non-negative CSS pixels. Never NaN.
 *
 * The invariant is stated because NaN does not throw: it silently drops the
 * `calc()` declaration it lands in and blanks the screen with a clean console.
 * `parseFloat` of a missing CSS env() var returns exactly that.
 */
/**
 * The CSS custom properties a stylesheet must mirror `env(safe-area-inset-*)`
 * onto, and the ONE place they are spelled.
 *
 * `env()` is not readable from script -- `getComputedStyle().getPropertyValue`
 * can only read a custom property -- so every webview-based shell reads these
 * names, and they have to be the same names.
 *
 * They were not. The Tauri shell read `--safe-area-inset-*` and the web shell
 * read `--sai-*`, so one of them was always going to find `""` on a real page,
 * parse it to 0, and lay content flush against the notch with no error
 * anywhere. The conformance suite could not catch it: each shell is driven
 * through its harness, so neither ever reads real CSS. Naming them once is
 * what makes that class of drift impossible rather than merely tested for.
 */
export const INSET_VARIABLES: Readonly<Record<keyof SafeAreaInsets, string>> = {
  top: "--safe-area-inset-top",
  right: "--safe-area-inset-right",
  bottom: "--safe-area-inset-bottom",
  left: "--safe-area-inset-left",
};

export interface SafeAreaInsets {
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
  readonly left: number;
}

export type LifecyclePhase = "active" | "inactive" | "background";

export type HapticKind = "selection" | "impact" | "success" | "warning" | "error";

export interface SharePayload {
  readonly text: string;
  readonly title?: string;
  readonly url?: string;
}

export interface ShellPort {
  readonly kind: ShellKind;

  /**
   * A synchronous snapshot, not a promise.
   *
   * First paint has to place the composer above the home indicator. An async
   * read paints once wrong and then jumps, which is the single most obvious
   * "this is a web page in a box" tell there is.
   */
  readonly insets: SafeAreaInsets;

  onInsetsChanged(cb: (insets: SafeAreaInsets) => void): Unsubscribe;

  /**
   * A synchronous snapshot, for the same reason `insets` is one.
   *
   * A component mounting while the keyboard is ALREADY up -- a warm resume, a
   * hardware or floating keyboard -- would otherwise lay out at 0 until the
   * next transition, paint once wrong, and jump. Events alone cannot express
   * "it is up right now", only "it just changed".
   *
   * Like `insets`, this must already reflect a change before the subscribers
   * of `onKeyboardHeightChanged` run.
   */
  readonly keyboardHeightPx: number;

  /** 0 when hidden. Fires through the show/hide transition, not just at its end. */
  onKeyboardHeightChanged(cb: (heightPx: number) => void): Unsubscribe;

  /**
   * Backgrounding must stop the render loop and flush the transcript.
   *
   * On iOS the app can be killed while suspended with no further callback, so
   * anything unflushed at this moment is simply lost.
   */
  onLifecycleChanged(cb: (phase: LifecyclePhase) => void): Unsubscribe;

  /**
   * Android's back gesture and iOS's edge swipe.
   *
   * The callback returns true if the app consumed it; false lets the OS act,
   * which on Android means exiting. A handler that always returns true traps
   * the user inside the app -- the router test asserts the root route returns
   * false for exactly this reason.
   *
   * HANDLERS ARE A STACK: the most recently registered gets first refusal, and
   * the first to return true wins. This is the entire difference between a
   * modal that closes and one left floating over the wrong screen, so it is
   * part of the contract rather than an implementation detail -- an adapter
   * storing handlers in a Set has no defined order and ships that bug.
   *
   * ORDERING: `insets` must already reflect a change before its subscribers
   * run, because every re-render re-reads the snapshot inside the callback.
   * A shell that notifies first lays out one rotation behind.
   */
  onBackGesture(cb: () => boolean): Unsubscribe;

  haptic(kind: HapticKind): void;

  share(payload: SharePayload): Promise<void>;

  /**
   * Hand a URL to the OS.
   *
   * MUST reject any scheme `isOpenableExternally` rejects. This is not
   * defensive tidiness: in a webview, `openExternal("javascript:...")` is
   * script execution in the app's OWN origin with the user's session -- and
   * the URL routinely comes from a model, a tool result, or a pasted message,
   * none of which are trusted. The rule lives here rather than in one adapter
   * so every shell is held to it by the contract suite.
   */
  openExternal(url: string): Promise<void>;
}

/**
 * Schemes that may be handed to the OS.
 *
 * An allowlist, never a blocklist. `javascript:` and `data:` are the obvious
 * hazards, but the set of dangerous schemes is open-ended and platform
 * specific -- `intent:` on Android, `file:` everywhere -- so enumerating the
 * safe ones is the only version that stays correct as platforms add more.
 */
export const OPENABLE_SCHEMES: readonly string[] = [
  "http", "https", "mailto", "tel", "sms", "geo", "maps",
];

export function isOpenableExternally(url: string): boolean {
  // A scheme-relative or relative URL has no scheme to trust.
  const match = /^([a-z][a-z0-9+.-]*):/i.exec(url.trim());
  if (match === null) return false;
  return OPENABLE_SCHEMES.includes(match[1]!.toLowerCase());
}
