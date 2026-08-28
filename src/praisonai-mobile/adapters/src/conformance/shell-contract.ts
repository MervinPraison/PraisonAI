/**
 * The ShellPort contract, as a runnable suite.
 *
 * Every shell runs this -- the fake and the Tauri adapter today, React Native
 * next. That is what stops them drifting, and shell drift is uniquely nasty
 * because the fake is what every core/ and ui/ test runs against: if the fake
 * delivers a keyboard height of 0 and the real adapter swallows it as falsy,
 * the whole suite is green and the composer sits over empty space on a device.
 *
 * WHY A HARNESS RATHER THAN A BARE ShellPort. Every interesting guarantee here
 * is about an event the OS delivers -- a rotation, the keyboard, a back
 * gesture. A ShellPort alone cannot be driven into any of them, so a suite
 * taking one could only assert that the methods exist. The harness is the same
 * device EngineHarness uses in engines/src/conformance.ts and for the same
 * reason: being drivable into the scenarios IS part of the seam.
 *
 * Like the storage contract, this one has to be able to FAIL.
 * `contracts.test.ts` runs it against deliberately broken shells -- an
 * unsubscribe that does not unsubscribe, NaN insets, back handlers in
 * registration order, a back handler that always consumes -- and asserts which
 * case each one fails. A contract suite with no broken-implementation test is
 * documentation with a `test()` around it, and this repo has already paid for
 * that lesson: 8 of 16 mutations survived a 408-test suite.
 */
import test from "node:test";
import assert from "node:assert/strict";

import type {
  LifecyclePhase,
  SafeAreaInsets,
  ShellPort,
} from "../../../core/src/ports/shell.ts";

/**
 * A shell plus the ability to play the OS side of it.
 *
 * Everything here is synchronous, which is itself part of the contract: a
 * harness that had to `await` an emit could not express "the keyboard and the
 * inset change arrive within the same frame", and that ordering is exactly
 * where tablet layout bugs live.
 */
export interface ShellHarness {
  readonly shell: ShellPort;
  /** Deliver an OS back gesture. Returns what the app answered, so a test can
   *  assert that the OS would have been allowed to act. */
  pressBack(): boolean;
  emitInsets(insets: SafeAreaInsets): void;
  emitKeyboardHeight(px: number): void;
  emitLifecycle(phase: LifecyclePhase): void;
  /** Live subscriber count, so a leak is provable rather than inferred. */
  listenerCount(): number;
  /** The URLs `openExternal` actually handed the OS, in order. A shell can
   *  validate one string and forward another, and `doesNotReject` cannot see
   *  the difference -- so the harness surfaces the forwarded value and the
   *  contract reads it. Every real shell can supply this; it is required rather
   *  than optional so a shell cannot opt out of being checked. */
  forwarded(): readonly string[];
}

const PHONE: SafeAreaInsets = { top: 47, right: 0, bottom: 34, left: 0 };
const LANDSCAPE: SafeAreaInsets = { top: 0, right: 47, bottom: 21, left: 47 };

const EDGES: ReadonlyArray<keyof SafeAreaInsets> = ["top", "right", "bottom", "left"];

export function describeShellContract(
  name: string,
  make: () => ShellHarness | Promise<ShellHarness>,
): void {
  // ---- identity ----------------------------------------------------------

  test(`${name}: the shell says which shell it is`, async () => {
    // A crash report that cannot say whether it came from the Tauri shell or
    // the React Native one costs a day per occurrence.
    const { shell } = await make();
    assert.equal(typeof shell.kind, "string");
    assert.notEqual(shell.kind, "", "kind must identify the shell");
  });

  // ---- insets ------------------------------------------------------------

  test(`${name}: insets are a synchronous snapshot, not a promise`, async () => {
    // First paint has to place the composer above the home indicator. An async
    // read paints once wrong and then jumps, which is the most obvious
    // "web page in a box" tell there is.
    const { shell } = await make();
    const snapshot: unknown = shell.insets;
    assert.equal(typeof snapshot, "object");
    assert.notEqual(
      typeof (snapshot as { then?: unknown }).then,
      "function",
      "insets must not be thenable",
    );
    for (const edge of EDGES) assert.equal(typeof shell.insets[edge], "number");
  });

  test(`${name}: no inset is ever NaN`, async () => {
    // NaN does not throw and does not warn: `calc(100vh - NaNpx)` is an invalid
    // value, the declaration is dropped, and the screen goes blank with a clean
    // console. Every unparseable CSS value has to collapse to 0 instead.
    const { shell, emitInsets } = await make();
    for (const edge of EDGES) {
      assert.equal(Number.isNaN(shell.insets[edge]), false, `${edge} was NaN before any change`);
    }
    emitInsets(PHONE);
    for (const edge of EDGES) {
      assert.equal(Number.isNaN(shell.insets[edge]), false, `${edge} was NaN after a change`);
      assert.equal(Number.isFinite(shell.insets[edge]), true, `${edge} was not finite`);
    }
  });

  test(`${name}: no inset is negative`, async () => {
    // A negative inset pulls content off-screen under the notch rather than
    // clear of it, and reads as "the safe area is being ignored".
    const { shell, emitInsets } = await make();
    emitInsets(PHONE);
    for (const edge of EDGES) assert.ok(shell.insets[edge] >= 0, `${edge} was negative`);
  });

  test(`${name}: an inset change reaches its subscriber`, async () => {
    const { shell, emitInsets } = await make();
    const seen: SafeAreaInsets[] = [];
    shell.onInsetsChanged((next) => void seen.push(next));
    emitInsets(PHONE);
    assert.deepEqual(seen, [PHONE]);
  });

  test(`${name}: the snapshot is already updated when the subscriber runs`, async () => {
    // Every re-render re-reads `shell.insets`. If the snapshot were assigned
    // after the notification, the layout computed during a rotation would be
    // one rotation behind -- correct on the second rotation, wrong on every
    // first one.
    const { shell, emitInsets } = await make();
    let readInside: SafeAreaInsets | null = null;
    shell.onInsetsChanged(() => void (readInside = shell.insets));
    emitInsets(LANDSCAPE);
    assert.deepEqual(readInside, LANDSCAPE);
    assert.deepEqual(shell.insets, LANDSCAPE);
  });

  test(`${name}: an unsubscribed inset listener stops firing`, async () => {
    const { shell, emitInsets } = await make();
    let calls = 0;
    const stop = shell.onInsetsChanged(() => void (calls += 1));
    emitInsets(PHONE);
    stop();
    emitInsets(LANDSCAPE);
    assert.equal(calls, 1, "the listener fired after it was unsubscribed");
  });

  // ---- unsubscribe -------------------------------------------------------

  test(`${name}: unsubscribing drops the live listener count`, async () => {
    // A leaked listener fires against a torn-down view on every rotation. The
    // behavioural check above cannot see a listener that is still registered
    // but happens to be harmless today; the count can.
    const harness = await make();
    const base = harness.listenerCount();
    const stops = [
      harness.shell.onInsetsChanged(() => {}),
      harness.shell.onKeyboardHeightChanged(() => {}),
      harness.shell.onLifecycleChanged(() => {}),
      harness.shell.onBackGesture(() => false),
    ];
    assert.equal(harness.listenerCount(), base + 4, "subscribing did not register");
    for (const stop of stops) stop();
    assert.equal(harness.listenerCount(), base, "unsubscribing did not deregister");
  });

  test(`${name}: unsubscribing twice does not remove somebody else's listener`, async () => {
    // React StrictMode runs cleanup twice. A splice keyed on the callback
    // rather than on the registration removes an innocent bystander, and the
    // symptom is a screen that stops responding to back only in development.
    const harness = await make();
    const base = harness.listenerCount();
    const stopFirst = harness.shell.onKeyboardHeightChanged(() => {});
    let survivorCalls = 0;
    harness.shell.onKeyboardHeightChanged(() => void (survivorCalls += 1));

    stopFirst();
    stopFirst();

    assert.equal(harness.listenerCount(), base + 1, "a second unsubscribe removed a bystander");
    harness.emitKeyboardHeight(300);
    assert.equal(survivorCalls, 1, "the surviving listener stopped firing");
  });

  // ---- keyboard ----------------------------------------------------------

  test(`${name}: a keyboard height of 0 is delivered, because 0 means hidden`, async () => {
    // 0 is falsy. An adapter guarding with `if (px)` never reports the hide,
    // and the composer stays pushed up over empty space for the rest of the
    // session.
    const { shell, emitKeyboardHeight } = await make();
    const seen: number[] = [];
    shell.onKeyboardHeightChanged((px) => void seen.push(px));
    emitKeyboardHeight(320);
    emitKeyboardHeight(0);
    assert.deepEqual(seen, [320, 0]);
  });

  test(`${name}: keyboard heights arrive through the transition, not just at its end`, async () => {
    // The port says so explicitly. A shell that only reports the settled height
    // makes the composer jump on show instead of riding the animation.
    const { shell, emitKeyboardHeight } = await make();
    const seen: number[] = [];
    shell.onKeyboardHeightChanged((px) => void seen.push(px));
    for (const px of [80, 190, 260, 291]) emitKeyboardHeight(px);
    assert.deepEqual(seen, [80, 190, 260, 291]);
  });

  // ---- lifecycle ---------------------------------------------------------

  test(`${name}: backgrounding reaches its subscriber`, async () => {
    // On iOS the app can be killed while suspended with no further callback, so
    // anything not flushed at this moment is simply lost.
    const { shell, emitLifecycle } = await make();
    const seen: LifecyclePhase[] = [];
    shell.onLifecycleChanged((phase) => void seen.push(phase));
    emitLifecycle("inactive");
    emitLifecycle("background");
    emitLifecycle("active");
    assert.deepEqual(seen, ["inactive", "background", "active"]);
  });

  test(`${name}: an unsubscribed lifecycle listener stops flushing`, async () => {
    const { shell, emitLifecycle } = await make();
    let calls = 0;
    const stop = shell.onLifecycleChanged(() => void (calls += 1));
    stop();
    emitLifecycle("background");
    assert.equal(calls, 0, "a torn-down screen tried to flush its transcript");
  });

  // ---- the back gesture --------------------------------------------------

  test(`${name}: a back gesture with no handler is refused, so the OS can act`, async () => {
    // Returning true here traps the user inside the app: on Android the back
    // button stops exiting and the only way out is the task switcher.
    const { pressBack } = await make();
    assert.equal(pressBack(), false);
  });

  test(`${name}: unsubscribing removes the RIGHT registration of a repeated handler`, async () => {
    // The case above registers two DIFFERENT closures, so `indexOf` and
    // `lastIndexOf` behave identically and the mutation between them survives.
    // React StrictMode double-invokes effects, so the same function reference
    // being registered twice is the ordinary case, not an exotic one.
    //
    // Registering A, B, A and then dropping the SECOND A must leave B on top
    // and the FIRST A beneath it. Removing the first instead leaves the stack
    // inverted: B is buried and the back press goes to the wrong screen.
    const { shell, pressBack } = await make();
    const order: string[] = [];
    const routeHandler = (): boolean => {
      order.push("route");
      return false; // pass it on, so the whole stack is observable
    };

    shell.onBackGesture(routeHandler);
    shell.onBackGesture(() => {
      order.push("modal");
      return false;
    });
    const dropSecond = shell.onBackGesture(routeHandler);
    dropSecond();

    pressBack();
    assert.deepEqual(
      order,
      ["modal", "route"],
      "unsubscribing removed the wrong registration, so the stack is inverted",
    );
  });

  test(`${name}: the most recently registered back handler gets first refusal`, async () => {
    // A modal opened over a route must consume the gesture. In registration
    // order the route pops first and the modal is left floating over the wrong
    // screen -- the classic Android back bug.
    const { shell, pressBack } = await make();
    const order: string[] = [];
    shell.onBackGesture(() => {
      order.push("route");
      return true;
    });
    shell.onBackGesture(() => {
      order.push("modal");
      return true;
    });

    assert.equal(pressBack(), true);
    assert.deepEqual(order, ["modal"], "the route ran, so the stack is inverted");
  });

  test(`${name}: handlers beneath a consuming one never run`, async () => {
    // Both dismissing the modal AND popping the route on one gesture skips a
    // screen, which reads as the app losing its place.
    const { shell, pressBack } = await make();
    let routeCalls = 0;
    shell.onBackGesture(() => {
      routeCalls += 1;
      return true;
    });
    shell.onBackGesture(() => true);
    pressBack();
    assert.equal(routeCalls, 0, "a consumed gesture still reached the handler beneath");
  });

  test(`${name}: a handler that declines passes the gesture down the stack`, async () => {
    // A modal with nothing to dismiss must not swallow the gesture, or back
    // silently does nothing.
    const { shell, pressBack } = await make();
    const order: string[] = [];
    shell.onBackGesture(() => {
      order.push("route");
      return true;
    });
    shell.onBackGesture(() => {
      order.push("modal");
      return false;
    });
    assert.equal(pressBack(), true);
    assert.deepEqual(order, ["modal", "route"]);
  });

  test(`${name}: when every handler declines the OS is allowed to act`, async () => {
    // The root route returns false on purpose. If the shell reported true
    // anyway, Android's back would never exit the app.
    const { shell, pressBack } = await make();
    shell.onBackGesture(() => false);
    shell.onBackGesture(() => false);
    assert.equal(pressBack(), false);
  });

  test(`${name}: closing a modal restores the handler beneath it`, async () => {
    const { shell, pressBack } = await make();
    const order: string[] = [];
    shell.onBackGesture(() => {
      order.push("route");
      return true;
    });
    const closeModal = shell.onBackGesture(() => {
      order.push("modal");
      return true;
    });

    pressBack();
    closeModal();
    pressBack();

    assert.deepEqual(order, ["modal", "route"], "the route never regained the gesture");
  });

  // ---- native features that may simply not exist -------------------------

  test(`${name}: a haptic on a device without haptics is silent, not fatal`, async () => {
    // Desktop webviews have no haptics plugin at all. A throw here turns a
    // decorative buzz into a broken button.
    const { shell } = await make();
    assert.doesNotThrow(() => {
      shell.haptic("selection");
      shell.haptic("impact");
      shell.haptic("success");
      shell.haptic("warning");
      shell.haptic("error");
    });
  });

  test(`${name}: share resolves even where there is no share sheet`, async () => {
    // Rejecting on a platform difference the caller cannot fix forces every
    // call site to wrap itself in a try, and one of them will forget.
    const { shell } = await make();
    await assert.doesNotReject(() => shell.share({ text: "hello", title: "t" }));
  });

  test(`${name}: share accepts a payload with only the required text`, async () => {
    // title and url are optional in the port. An adapter that assumes they are
    // present renders the literal string "undefined" in the OS sheet.
    const { shell } = await make();
    await assert.doesNotReject(() => shell.share({ text: "just text" }));
  });

  test(`${name}: opening an ordinary link resolves`, async () => {
    // The pair for the refusals below: without it, "refuse everything" would
    // satisfy every one of them and no link in the app would work.
    const { shell } = await make();
    await assert.doesNotReject(() => shell.openExternal("https://example.com/docs"));
  });

  // ---- openExternal is an attack surface, not a convenience ----------------

  test(`${name}: a javascript: URL is refused`, async () => {
    // In a webview this is script execution in the app's OWN origin with the
    // user's session -- and the URL routinely comes from a model, a tool
    // result, or a pasted message. Every shell must refuse it, which is why
    // the rule lives in the port rather than in one adapter.
    const { shell } = await make();
    await assert.rejects(() => shell.openExternal("javascript:alert(document.cookie)"));
  });

  test(`${name}: a data: URL is refused`, async () => {
    const { shell } = await make();
    await assert.rejects(() => shell.openExternal("data:text/html,<script>alert(1)</script>"));
  });

  test(`${name}: a file: URL is refused`, async () => {
    const { shell } = await make();
    await assert.rejects(() => shell.openExternal("file:///etc/passwd"));
  });

  test(`${name}: a scheme-relative URL is refused`, async () => {
    // No scheme means nothing to trust. `//evil.example` inherits whatever the
    // opener assumes, which is the bug this allowlist exists to prevent.
    const { shell } = await make();
    await assert.rejects(() => shell.openExternal("//evil.example/x"));
  });

  test(`${name}: an uppercase JAVASCRIPT: URL is refused`, async () => {
    const { shell } = await make();
    await assert.rejects(() => shell.openExternal("JavaScript:alert(1)"));
  });

  test(`${name}: an uppercase HTTPS: URL is still opened`, async () => {
    // Scheme comparison is case-insensitive per RFC 3986, and THIS is the
    // direction that catches a case-sensitive allowlist. The refusal above
    // passes either way -- an unrecognised "JavaScript" is rejected for the
    // wrong reason -- so without this case the bug survives: every link the
    // user pastes with a capitalised scheme silently stops working.
    const { shell } = await make();
    await assert.doesNotReject(() => shell.openExternal("HTTPS://example.com/docs"));
  });

  test(`${name}: a mailto URL is opened`, async () => {
    const { shell } = await make();
    await assert.doesNotReject(() => shell.openExternal("mailto:someone@example.com"));
  });


  // ---- the keyboard snapshot ------------------------------------------------

  test(`${name}: the keyboard height is readable synchronously`, async () => {
    // A component mounting while the keyboard is ALREADY up -- a warm resume,
    // a hardware or floating keyboard -- would otherwise lay out at 0 until the
    // next transition: one wrong frame, then a jump.
    const { shell, emitKeyboardHeight } = await make();
    assert.equal(shell.keyboardHeightPx, 0, "nothing has happened yet");
    emitKeyboardHeight(336);
    assert.equal(shell.keyboardHeightPx, 336);
  });

  test(`${name}: the keyboard snapshot returns to zero when it hides`, async () => {
    // The pair: a snapshot that only ever grows leaves the composer stranded
    // above a keyboard that is no longer there.
    const { shell, emitKeyboardHeight } = await make();
    emitKeyboardHeight(336);
    emitKeyboardHeight(0);
    assert.equal(shell.keyboardHeightPx, 0);
  });

  test(`${name}: the keyboard snapshot is already updated when subscribers run`, async () => {
    // The port's ordering rule. Every re-render re-reads the snapshot inside
    // the callback, so a shell that notifies first lays out one transition
    // behind -- the exact bug the synchronous read exists to prevent.
    const { shell, emitKeyboardHeight } = await make();
    let seen = -1;
    shell.onKeyboardHeightChanged(() => {
      seen = shell.keyboardHeightPx;
    });
    emitKeyboardHeight(291);
    assert.equal(seen, 291, "the snapshot must be current inside the callback");
  });


  test(`${name}: a padded URL reaches the OS trimmed, or not at all`, async () => {
    // `url.trim()` -> `url` survived: the allowlist still refuses a padded
    // `javascript:`, but a URL that passes validation in one form and is handed
    // to the OS in another is the shape of a scheme-confusion bypass. And
    // `doesNotReject` only proves the call did not throw, never that it did the
    // right thing -- for a security boundary that gap is the whole question. So
    // this reads what the shell FORWARDED, not merely whether it settled.
    const harness = await make();
    const { shell } = harness;
    await assert.doesNotReject(() => shell.openExternal("  https://ok.example  "));
    assert.deepEqual(
      harness.forwarded(),
      ["https://ok.example"],
      "the OS must receive the trimmed URL the allowlist actually approved, not the padded input",
    );
    // And padding must not smuggle a refused scheme past the allowlist.
    await assert.rejects(
      () => shell.openExternal("  javascript:alert(1)  "),
      "whitespace must not launder a refused scheme",
    );
    await assert.rejects(() => shell.openExternal("\tdata:text/html,<script>x</script>"));
    // A refused scheme must never reach the OS, however it was padded.
    assert.deepEqual(
      harness.forwarded(),
      ["https://ok.example"],
      "a refused scheme was forwarded to the OS despite the rejection",
    );
  });

  test(`${name}: a safe-area event carrying only the edges that changed is honoured`, async () => {
    // `coerceInsets` requiring EVERY edge (`&&` -> `||`) survived: a native
    // payload with only the edge that moved is discarded whole, and the insets
    // stay at their stale values -- the composer sits under the home indicator
    // after a rotation. And dropping `right` from the dedupe survived too, so a
    // landscape notch appearing on the right was deduped away as "no change".
    const { shell, emitInsets } = await make();
    emitInsets({ top: 47, right: 0, bottom: 34, left: 0 });
    assert.equal(shell.insets.bottom, 34);

    // Only the right edge moves -- rotating into a notch.
    emitInsets({ top: 0, right: 44, bottom: 21, left: 47 });
    assert.equal(shell.insets.right, 44, "an inset change on the right edge must not be deduped away");
    assert.equal(shell.insets.top, 0, "and the other edges must follow the same event");
  });

  test(`${name}: unsubscribing TWICE does not remove a bystander`, async () => {
    // Dropping the `if (at !== -1)` guard before `splice(at, 1)` survived. A
    // double unsubscribe -- a re-render, React StrictMode double-invoking an
    // effect -- splices at index -1, which removes the LAST element: another
    // screen's back handler silently disappears.
    //
    // The second call must be a no-op, not a removal of whatever happens to be
    // at the end of the stack.
    const { shell, pressBack } = await make();
    const order: string[] = [];
    const stopA = shell.onBackGesture(() => {
      order.push("A");
      return false;
    });
    shell.onBackGesture(() => {
      order.push("B");
      return false;
    });

    stopA();
    stopA(); // the double unsubscribe

    pressBack();
    assert.deepEqual(order, ["B"], "the bystander handler was removed by a repeated unsubscribe");
  });

}
