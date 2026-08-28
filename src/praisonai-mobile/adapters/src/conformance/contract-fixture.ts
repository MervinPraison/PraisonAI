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
import { describeStorageContract } from "./storage-contract.ts";
import { describeTimeContract } from "./time-contract.ts";
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

describeSecretsContract("fixture secrets", () => secrets());
describeStorageContract("fixture storage", () => storage());
describeTimeContract("fixture time", () => time(), advance, true);
