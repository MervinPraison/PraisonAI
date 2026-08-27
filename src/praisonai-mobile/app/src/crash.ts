/**
 * The last line of defence.
 *
 * There was no `window.onerror` and no `unhandledrejection` handler anywhere,
 * so a throw inside a click handler produced a UI that simply stopped
 * responding -- no message, no recovery, and on a phone no console to read.
 * That is the failure mode this whole package is built against, sitting at the
 * one layer that had no cover.
 *
 * Two rules, both learned the hard way:
 *
 *  - It reports, it does not swallow. The error is re-logged so a device log
 *    or a remote console still has it; a handler that quietly absorbs
 *    everything turns a crash into a mystery.
 *  - It fires ONCE. A crash often cascades -- the failed render throws again
 *    on the next frame -- and a handler that repaints the crash screen every
 *    time turns one fault into a loop that pins the CPU.
 */
export interface CrashDeps {
  readonly view?: Window;
  /** Draw the crash screen. Called at most once. */
  readonly onCrash: (error: unknown) => void;
  /** Injected so a test can assert what was reported without a real console. */
  readonly report?: (label: string, error: unknown) => void;
}

export interface CrashHandle {
  /** Whether the handler has already fired. */
  crashed(): boolean;
  remove(): void;
}

export function installCrashHandler(deps: CrashDeps): CrashHandle {
  const view = deps.view ?? globalThis.window;
  const report = deps.report ?? ((label, error) => console.error(label, error));
  let crashed = false;

  const fire = (label: string, error: unknown): void => {
    report(label, error);
    if (crashed) return; // one screen, however many faults follow
    crashed = true;
    try {
      deps.onCrash(error);
    } catch (nested) {
      // The crash screen itself failed. Nothing further is safe to attempt,
      // and looping here would be worse than a blank page.
      report("crash-screen-failed", nested);
    }
  };

  const onError = (event: ErrorEvent): void => fire("uncaught", event.error ?? event.message);
  const onRejection = (event: PromiseRejectionEvent): void => fire("unhandled-rejection", event.reason);

  view?.addEventListener("error", onError);
  view?.addEventListener("unhandledrejection", onRejection);

  return {
    crashed: () => crashed,
    remove() {
      view?.removeEventListener("error", onError);
      view?.removeEventListener("unhandledrejection", onRejection);
    },
  };
}
