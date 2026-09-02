/**
 * The settings and the engines, as data.
 *
 * These two registries were the missing half of "swappable". Every port,
 * conformance suite and view model existed; nothing declared what the app
 * actually offers, so no code path could produce a live answer and a settings
 * screen had no key list to render. `SettingDef[]` was an injected parameter
 * that only a test ever supplied.
 *
 * Both live in `app/` deliberately. They are the only place that names a
 * concrete engine or a concrete setting, which is what keeps every layer below
 * unable to tell one engine from another.
 */
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";
import type { HttpPort } from "../../core/src/ports/http.ts";
import type { IgnoredReason } from "../../protocol/src/decode.ts";
import type { SettingDef, SettingsFacade } from "../../core/src/settings/store.ts";
import { createRemoteHttpEngine, probeHealth } from "../../engines/src/remote-http/engine.ts";
import type { EngineChoice } from "./engines.ts";
import type { RunPersistence } from "../../engines/src/praisonai-ts/engine.ts";

export const ENGINE_REMOTE_HTTP = "remote-http";
export const ENGINE_PRAISONAI_TS = "praisonai-ts";

/**
 * What the app offers, with the metadata a screen needs to draw a control.
 *
 * `label` rather than the key, because a settings screen showing `maxSteps` to
 * a user is a screen written by someone who never opened it.
 *
 * ONLY SETTINGS THE SHIPPING APP ACTUALLY READS BELONG HERE. `model`,
 * `temperature`, `showReasoning`, `showDiagnostics` and `apiKey` were declared
 * ahead of consumers that do not exist -- no code path read any of them (issue
 * #4636). A declared-but-unread setting is a control the UI promises and the
 * app does not keep: moving it does nothing, and `showDiagnostics`'s `false`
 * default even described a hiding that never happened, since the dropped row is
 * rendered unconditionally. They are removed rather than half-wired; the
 * store's secret and validation machinery stays (it is contract-tested) so a
 * real setting can be added the day its consumer does. `registry.test.ts` pins
 * that every declared key is one the app reads, so re-adding an inert one fails.
 */
export const SETTING_DEFS: readonly SettingDef[] = [
  {
    key: "engineId",
    default: ENGINE_REMOTE_HTTP,
    label: "Engine",
    help: "Which agent runtime answers. Remote talks to a PraisonAI engine over HTTP; in-process runs the agent loop on this device.",
    section: "Engine",
    // Only what `enginesFor` can actually build in the shipping composition.
    // ENGINE_PRAISONAI_TS was listed here and is only pushed when
    // `createInProcess` is supplied, which main.ts does not do -- so selecting
    // it persisted an id `selectEngine` then rejects, and the NEXT launch died
    // at `renderFatal` with no way back except editing storage by hand. A
    // picker must not offer a choice that bricks the app.
    choices: [ENGINE_REMOTE_HTTP],
  },
  {
    key: "baseUrl",
    default: "http://127.0.0.1:8765",
    label: "Engine address",
    help: "Only used by the remote engine.",
    section: "Engine",
  },
];

/** The keys the shipping app actually reads. `engineId` in `boot.ts`, `baseUrl`
 *  in `enginesFor` below. Exported so the test that forbids an inert setting
 *  compares `SETTING_DEFS` against a list an author has to consciously extend
 *  in the same commit that adds the code reading the new key. */
export const CONSUMED_SETTING_KEYS: readonly string[] = ["engineId", "baseUrl"];

export interface RegistryDeps {
  readonly settings: SettingsFacade;
  readonly http: HttpPort;
  /**
   * Builds the in-process engine.
   *
   * Injected rather than imported, because `praisonai` is not a dependency of
   * this package and cannot be until it is bundleable for a webview -- issue
   * #4437: `crypto` and `events` are static imports on its Agent graph, so the
   * bundle dies at import time before any code runs. Keeping it an injection
   * means the app builds and runs today with the remote engine, and gains the
   * in-process one by passing a factory rather than by a refactor.
   */
  readonly createInProcess?: (persistence: RunPersistence) => AgentEnginePort | Promise<AgentEnginePort>;
  /**
   * Where a completed turn is written.
   *
   * Passed to the in-process engine, which is what makes `end.userIndex` real:
   * the engine records the turn and reports the indices it actually wrote.
   * Without this the session existed, the engine's `persistence` port existed,
   * and NOTHING connected them -- so `record()` never ran in a real turn and no
   * conversation was ever saved.
   *
   * The remote engine deliberately does not take it: the server it talks to
   * persists, and it is the only thing that can report indices for its own
   * store. Two engines, two owners of the write, one honest `userIndex`.
   */
  readonly persistence: RunPersistence;
  /** Called for every frame an engine's decoder refuses. Supplied by the
   *  composition root, which owns the transcript those refusals land on. */
  readonly onIgnored?: (reason: IgnoredReason, detail: string) => void;
}

function stringSetting(settings: SettingsFacade, key: string, fallback: string): string {
  const value = settings.get(key);
  return typeof value === "string" && value !== "" ? value : fallback;
}

/**
 * Every engine the app can select, in the order a picker should show them.
 *
 * An engine whose prerequisites are absent is OMITTED rather than offered and
 * then failed: a picker listing a choice that cannot work is a support ticket.
 * `selectEngine` already reports "no engine X; available: ..." for an id that
 * is not here, which is the honest message in that case.
 */
export function enginesFor(deps: RegistryDeps): readonly EngineChoice[] {
  const baseUrl = stringSetting(deps.settings, "baseUrl", "http://127.0.0.1:8765").replace(/\/+$/, "");
  const choices: EngineChoice[] = [
    {
      id: ENGINE_REMOTE_HTTP,
      create: () =>
        createRemoteHttpEngine({
          baseUrl,
          http: deps.http,
          id: ENGINE_REMOTE_HTTP,
          // Refused frames go to the transcript instead of the floor.
          ...(deps.onIgnored === undefined ? {} : { onIgnored: deps.onIgnored }),
        }),
      // The check the whole readiness module exists for. A 200 with
      // `{"ok": false}` is the engine saying it is NOT ready, so trusting the
      // status alone routes a chat into a broken engine and reports the
      // nonsense back as a model failure. Run at selection, before the engine
      // is offered -- the in-process engine has no remote and supplies none.
      probe: () => probeHealth(deps.http, baseUrl),
    },
  ];

  if (deps.createInProcess !== undefined) {
    const build = deps.createInProcess;
    choices.push({ id: ENGINE_PRAISONAI_TS, create: () => build(deps.persistence) });
  }
  return choices;
}
