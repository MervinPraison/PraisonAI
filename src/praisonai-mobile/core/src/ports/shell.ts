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
   */
  onBackGesture(cb: () => boolean): Unsubscribe;

  haptic(kind: HapticKind): void;

  share(payload: SharePayload): Promise<void>;

  openExternal(url: string): Promise<void>;
}
