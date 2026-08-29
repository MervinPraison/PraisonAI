/**
 * An adapter broken in ONE named way, registered against the REAL contract.
 *
 * Not a `.test.ts`, so the normal run never picks it up. `contracts.test.ts`
 * spawns it once per break mode and asserts the matching contract case fails
 * BY NAME -- and asserts the `none` mode passes, so a runner that reported
 * failure for everything could not masquerade as proof.
 *
 * WHY THIS EXISTS. `contracts.test.ts` had a set of tests named "the contract
 * catches an adapter that ..." which built a broken adapter and then
 * RE-IMPLEMENTED the contract's assertion inline. Those prove that an
 * assertion of that shape would catch the defect. They prove nothing about
 * whether the contract still contains it.
 *
 * Measured: deleting `assert.ok(fired >= 2)` from the time contract -- the one
 * assertion that catches `setInterval` becoming `setTimeout`, which stops
 * every polling loop in the app after one tick -- left the suite at 1035 pass,
 * 0 fail. Fourteen separate assertions could be deleted for free, across all
 * four contracts, old and new alike. An entire section of the time contract
 * could be removed and the run simply reported one test fewer.
 *
 * The identical pattern already existed one directory over, in
 * engines/src/contract-fixture.ts, written for the same reason. The adapter
 * contracts never got it.
 *
 *   node adapters/src/conformance/contract-fixture.ts <mode>
 */
import { describeSecretsContract } from "./secrets-contract.ts";
import { describeShellContract, type ShellHarness } from "./shell-contract.ts";
import { describeStorageContract } from "./storage-contract.ts";
import { describeTimeContract } from "./time-contract.ts";
import { createWebShell } from "../web/shell.ts";
import { createFakeWindow } from "../web/fake-window.ts";
import type { SecretsPort } from "../../../core/src/ports/secrets.ts";
import type { StoragePort } from "../../../core/src/ports/storage.ts";
import type { TimePort } from "../../../core/src/ports/time.ts";

const mode = process.argv[2] ?? "none";

const advance = async (_time: TimePort, ms: number): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, ms + 10));
};

// ---- secrets ---------------------------------------------------------------

function secrets(): SecretsPort {
  const store = new Map<string, string>();
  // The defect: keying by slot alone, so two accounts share one credential.
  const key = (ref: { slot: string; account: string }): string =>
    mode === "secrets_slot_only" ? ref.slot : `${ref.slot}:${ref.account}`;
  return {
    isHardwareBacked: false,
    async has(ref) {
      return mode === "secrets_empty_is_absent"
        ? (store.get(key(ref)) ?? "") !== ""
        : store.has(key(ref));
    },
    async get(ref) {
      return store.get(key(ref)) ?? null;
    },
    async set(ref, value) {
      store.set(key(ref), value);
    },
    async delete(ref) {
      store.delete(key(ref));
    },
  };
}

// ---- storage ---------------------------------------------------------------

function storage(): StoragePort {
  // Inline rather than importing a fake: `adapters` may not import `testing`,
  // and the layer rule is right to say so. The engine fixture one directory
  // over builds its broken engines the same way.
  const files = new Map<string, string>();
  const key = (ref: { namespace: string; id: string }): string =>
    mode === "storage_namespaces_collide" ? ref.id : `${ref.namespace}/${ref.id}`;
  return {
    async read(ref) {
      const found = files.get(key(ref));
      // The defect: `||` instead of `??`, so a deliberately-blank value reads
      // back as "not configured" on every read.
      if (mode === "storage_empty_is_absent" && found === "") return null;
      if (found !== undefined) return found;
      return mode === "storage_missing_is_undefined" ? (undefined as never) : null;
    },
    async write(ref, value) {
      files.set(key(ref), value);
    },
    async remove(ref) {
      files.delete(key(ref));
    },
    async listIds(namespace) {
      if (mode === "storage_namespaces_collide") return [...files.keys()];
      const prefix = `${namespace}/`;
      return [...files.keys()]
        .filter((k) => k.startsWith(prefix))
        .map((k) => k.slice(prefix.length));
    },
    async clear(namespace) {
      if (mode === "storage_namespaces_collide") return void files.clear();
      const prefix = `${namespace}/`;
      for (const k of [...files.keys()]) if (k.startsWith(prefix)) files.delete(k);
    },
  };
}

// ---- time ------------------------------------------------------------------

function time(): TimePort {
  // Real timers, like the web adapter -- so the fixture needs no fake, and the
  // contract is driven exactly as it drives the shipping implementation.
  return {
    nowMs: () => performance.now(),
    epochMs: () => Date.now(),
    createScheduler() {
      let timer: ReturnType<typeof setTimeout> | null = null;
      return {
        requestFrame(cb) {
          setTimeout(cb, 0);
        },
        setTimer(cb, ms) {
          timer = setTimeout(cb, ms);
        },
        clearTimer() {
          // The defect: a clear that does not clear, so a cancelled fallback
          // timer still reopens a gate that was deliberately shut.
          if (mode === "time_clear_does_nothing") return;
          if (timer !== null) clearTimeout(timer);
          timer = null;
        },
      };
    },
    every(ms, cb) {
      if (mode === "time_unsubscribe_does_nothing") {
        // The defect: the interval leaks for the app's lifetime, and nothing
        // the caller does can stop it.
        const handle = setInterval(cb, ms);
        return () => {};
      }
      if (mode === "time_every_fires_once") {
        // The defect: every polling loop in the app fires once and stops.
        const handle = setTimeout(cb, ms);
        return () => clearTimeout(handle);
      }
      const handle = setInterval(cb, ms);
      return () => clearInterval(handle);
    },
  };
}

// ---- shell ------------------------------------------------------------------
//
// The largest of the four contracts -- 33 cases, including seven `openExternal`
// refusals -- and it was the ONE this fixture did not register. A re-measure
// proved the consequence: every assertion in it could be deleted, the whole
// security section removed, and the entire contract replaced with
// `assert.ok(shell)`, with the suite green each time.
//
// A `javascript:` URL reaching `openExternal` inside a webview is script
// execution in the app's own origin with the user's session, from a URL that
// routinely arrives from a model, a tool result, or pasted text. The RULE lives
// in core/src/ports/shell.ts and both adapters call it; the contract proving
// each adapter calls it is what was undefended.
//
// Built by wrapping a real web shell rather than hand-rolling a ShellPort, so
// the fixture cannot drift from the interface it is meant to exercise.
function shellHarness(): ShellHarness {
  const window = createFakeWindow();
  const real = createWebShell(window.window);

  const shell = {
    ...real,
    get insets() {
      // The defect: a negative inset reaching the layout, which lifts content
      // off the wrong edge.
      if (mode === "shell_negative_insets") return { top: -5, right: 0, bottom: -5, left: 0 };
      return real.insets;
    },
    get keyboardHeightPx() { return real.keyboardHeightPx; },
    onInsetsChanged: real.onInsetsChanged.bind(real),
    onKeyboardHeightChanged: real.onKeyboardHeightChanged.bind(real),
    onLifecycleChanged: real.onLifecycleChanged.bind(real),
    haptic: real.haptic.bind(real),
    share: real.share.bind(real),

    async openExternal(url: string): Promise<void> {
      // The defect: a case-SENSITIVE allowlist. `JAVASCRIPT:` then slips past
      // a guard that refuses `javascript:`, which is the oldest trick there is.
      if (mode === "shell_scheme_case_sensitive" && /^[A-Z]/.test(url.trim())) {
        window.window.open(url, "_blank", "noopener,noreferrer");
        return;
      }
      // The defect: opening whatever it is handed. `javascript:`, `data:` and
      // `file:` all reach the OS.
      if (mode === "shell_opens_anything") {
        window.window.open(url, "_blank", "noopener,noreferrer");
        return;
      }
      return real.openExternal(url);
    },

    onBackGesture(cb: () => boolean) {
      // The defect: the FIRST handler registered answers, rather than the most
      // recent. A screen pushed on top of another then never gets the back
      // press -- the bystander bug the contract has a named case for.
      if (mode === "shell_back_in_registration_order") {
        backHandlers.push(cb);
        return () => {
          const at = backHandlers.indexOf(cb);
          if (at !== -1) backHandlers.splice(at, 1);
        };
      }
      return real.onBackGesture(cb);
    },

    pressBack(): boolean {
      if (mode === "shell_back_in_registration_order") {
        for (const handler of backHandlers) if (handler()) return true;
        return false;
      }
      return real.pressBack();
    },

    listenerCount(): number {
      // The defect: a leak that cannot be seen. An unsubscribed listener still
      // counts, so "unsubscribing drops the live listener count" cannot fail.
      if (mode === "shell_listener_count_stuck") return 0;
      return real.listenerCount();
    },
  } as typeof real;

  const backHandlers: (() => boolean)[] = [];

  return {
    shell,
    pressBack: () => shell.pressBack(),
    emitInsets: (insets) => window.setInsets(insets),
    emitKeyboardHeight: (px) => window.setKeyboardHeight(px),
    emitLifecycle: (phase) => {
      if (phase === "background") window.setHidden(true);
      else if (phase === "inactive") window.setFocused(false);
      else window.setHidden(false);
    },
    listenerCount: () => shell.listenerCount(),
    forwarded: () => window.opened,
  };
}

describeSecretsContract("fixture secrets", () => secrets());
describeStorageContract("fixture storage", () => storage());
describeTimeContract("fixture time", () => time(), advance, true);
describeShellContract("fixture shell", shellHarness);
