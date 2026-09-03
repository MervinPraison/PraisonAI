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
import type { SecretsPort } from "../../core/src/ports/secrets.ts";
import { readSecretSetting, type SettingDef, type SettingsFacade } from "../../core/src/settings/store.ts";
import type { Platform } from "./platform.ts";
import { createRemoteHttpEngine, probeHealth } from "../../engines/src/remote-http/engine.ts";
import type { EngineChoice } from "./engines.ts";
import type { ConversationHistory, RunPersistence } from "../../engines/src/praisonai-ts/engine.ts";

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
 * rendered unconditionally. They were removed rather than half-wired; the
 * store's secret and validation machinery stayed (it is contract-tested) so a
 * real setting could be added the day its consumer did. `registry.test.ts` pins
 * that every declared key is one the app reads, so re-adding an inert one fails.
 *
 * `openaiApiKey` is that day, and it arrives with its consumer in the same
 * commit rather than ahead of one: `apiKeyFor` below reads it back through the
 * keychain port, and `createInProcessEngine` in main.ts hands it to the agent
 * on every turn. Before it, the app launched, loaded its engine, and failed
 * the first message with "The OPENAI_API_KEY environment variable is missing or
 * empty" -- with no field anywhere in the app to put one in.
 */
export const SETTING_DEFS: readonly SettingDef[] = [
  {
    key: "engineId",
    default: ENGINE_REMOTE_HTTP,
    label: "Engine",
    help: "Which agent runtime answers. Remote talks to a PraisonAI engine over HTTP; in-process runs the agent loop on this device.",
    section: "Engine",
    // Exactly what `appEngines` in main.ts can build -- registry.test.ts
    // compares this list against that composition, because a picker offering
    // an id `selectEngine` rejects is a dead end: the choice persists, the
    // NEXT launch cannot build it, and boot dies at `renderFatal` with no way
    // back except editing storage by hand. That is what happened when
    // ENGINE_PRAISONAI_TS was listed here while nothing supplied
    // `createInProcess`. It is back because main.ts supplies the factory and
    // the engine ships as a chunk beside app.js (engines/praisonai-ts/
    // load-agent.ts).
    //
    // `default` here is the WEB default; `settingDefsFor` swaps in the
    // platform's, so the value Settings shows and the engine that answers a
    // first launch are the same one.
    choices: [ENGINE_REMOTE_HTTP, ENGINE_PRAISONAI_TS],
  },
  {
    key: "baseUrl",
    default: "http://127.0.0.1:8765",
    label: "Engine address",
    help: "Only used by the remote engine.",
    section: "Engine",
  },
  /**
   * The one credential the shipping app can actually use.
   *
   * ONE slot, not five. `SecretSlot` is a closed union of openai | anthropic |
   * google | openrouter | custom, and it is closed for a keychain-namespace
   * reason (ports/secrets.ts rule 3), not as an instruction to ship five rows
   * on day one. The in-process engine builds exactly one kind of agent -- see
   * `createInProcessEngine` in main.ts, whose model falls back to
   * `gpt-4o-mini`, which praisonai-ts routes through its OpenAIService -- so
   * `openai` is the only slot with a reader. An `anthropic` row would be a
   * control nobody reads, which is exactly the #4636 defect the test below
   * forbids and exactly what `apiKey` was before it was removed. The other
   * four slots stay available for the commit that adds a provider setting AND
   * the code that honours it, in that order.
   *
   * `secret: true` routes it to SecretsPort and never to the settings file
   * (store.ts, and its test asserting the fake StoragePort never saw the
   * value). `secretRef` is what says WHERE, in the registry that declares it,
   * rather than in whoever happened to build the view.
   *
   * `default: ""` is never stored and never shown: a secret def has no value
   * row at all (view-model.ts rule 1). It is here because `SettingDef.default`
   * is required, and "" is the only honest stand-in for "there isn't one".
   */
  {
    key: "openaiApiKey",
    default: "",
    label: "OpenAI API key",
    help: "Used by the in-process engine. Kept in the platform secret store, never in the settings file, and never shown back to you.",
    section: "Engine",
    secret: true,
    secretRef: { slot: "openai", account: "default" },
  },
];

/** The keys the shipping app actually reads. `engineId` in `boot.ts`, `baseUrl`
 *  in `enginesFor` below. Exported so the test that forbids an inert setting
 *  compares `SETTING_DEFS` against a list an author has to consciously extend
 *  in the same commit that adds the code reading the new key. */
/**
 * The engine to start with when settings name none, by platform.
 *
 * On a device, the in-process engine: a phone has no `127.0.0.1:8765` to
 * reach, and a cleartext localhost address is refused by iOS ATS and Android
 * besides, so the remote default was a first prompt that failed with a status
 * code. Now that the engine ships as a chunk beside app.js, it is the one
 * choice that works with nothing configured -- up to the model itself, which
 * still needs a key the app has no setting for yet.
 *
 * On the web, the remote engine: there is a server to talk to, and no reason
 * to fetch 1.3MB of engine into a browser tab first. `Platform["kind"]` is
 * only `"tauri" | "web"`, so desktop Tauri (`cargo tauri dev`) counts as a
 * device here and starts in-process too; a developer with a server running
 * switches in Settings, and the persisted `engineId` wins over this
 * (`chosenStringOr` in boot.ts), so it only ever decides the very first launch.
 *
 * Exported, and called by `settingDefsFor`, so the boot fallback and the
 * def's `default` cannot disagree -- Settings would show one engine while
 * another answered.
 */
export function defaultEngineIdFor(kind: Platform["kind"]): string {
  return kind === "tauri" ? ENGINE_PRAISONAI_TS : ENGINE_REMOTE_HTTP;
}

/** SETTING_DEFS with the engine default the platform actually starts on. */
export function settingDefsFor(kind: Platform["kind"]): readonly SettingDef[] {
  return SETTING_DEFS.map((def) =>
    def.key === "engineId" ? { ...def, default: defaultEngineIdFor(kind) } : def,
  );
}

export const CONSUMED_SETTING_KEYS: readonly string[] = ["engineId", "baseUrl", "openaiApiKey"];

/**
 * The credential the in-process engine authenticates with, or null.
 *
 * The first non-test caller of `SecretsPort.get` in this package. Everything
 * needed to store a key existed -- the `secret` flag, the routing in
 * store.ts, the keychain port, its conformance suite -- and nothing read one
 * back, so a key the user typed went into the store and stopped there.
 *
 * It takes the full port, not the `SettingsFacade`: the facade has no getter
 * by design, so this function is unreachable from `ui/` with what `ui/` is
 * handed. That is rule 2 of ports/secrets.ts enforced by a signature rather
 * than by a review.
 *
 * The DEFS are passed in rather than read from `SETTING_DEFS`, so this follows
 * the same list the settings screen was rendered from -- `settingDefsFor`
 * rewrites one def per platform, and a resolver reading a different list from
 * the one the screen shows is how a setting stops meaning what it says.
 *
 * Called per TURN (see main.ts), never captured at boot: `enginesFor` learned
 * that lesson with `baseUrl`, where a value read once at construction meant a
 * corrected setting could not take effect without force-quitting the app. A
 * key pasted into Settings must work on the very next message.
 */
export function apiKeyFor(
  secrets: SecretsPort,
  defs: readonly SettingDef[],
): Promise<string | null> {
  return readSecretSetting(secrets, defs, "openaiApiKey");
}

export interface RegistryDeps {
  readonly settings: SettingsFacade;
  readonly http: HttpPort;
  /**
   * Builds the in-process engine.
   *
   * Injected rather than imported, because tools/boundaries.json lets only
   * engines/src/praisonai-ts name `praisonai` -- that seam is what makes the
   * framework swappable, and this file sits above it. The injection is also
   * what let the app build and run with the remote engine while the in-process
   * one could not be bundled for a webview at all (#4437: `crypto` and
   * `events` were static imports on its Agent graph). Now `praisonai/mobile`
   * ships as a lazy chunk and main.ts supplies the factory; the injection
   * stays because the boundary does.
   */
  readonly createInProcess?: (
    persistence: RunPersistence,
    history: ConversationHistory,
  ) => AgentEnginePort | Promise<AgentEnginePort>;
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
  /**
   * Where the conversation so far is READ from.
   *
   * The counterpart of `persistence`, and it goes to exactly the same engines
   * for exactly the same reason. The in-process engine owns its store, so it
   * must replay it or the model has no memory of a chat the app is displaying.
   * The remote engine deliberately does not take it: the server it talks to
   * keeps its own history against the `chat_id` every request carries, so
   * sending the client's copy as well would send every prior turn twice.
   *
   * Two engines, two owners of the conversation -- the same split this file
   * already draws for the write, drawn once for the read.
   */
  readonly history: ConversationHistory;
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
  /**
   * The engine address, read at the moment it is USED.
   *
   * This was a `const` read once, here, and both the engine and the probe
   * closed over the string. The app builds its engine exactly once, at boot
   * (boot.ts), and holds it for the session -- so a phone that could not reach
   * `127.0.0.1:8765` kept sending there no matter what was typed into
   * Settings. The value persisted, the screen agreed, and only a relaunch
   * changed anything: a recovery path that requires force-quitting the app.
   *
   * Rebuilding the engine on the change was the alternative, and it is a much
   * larger one: `createRunController` takes the engine at construction and
   * there is no seam to swap it, so following the setting that way means
   * rebuilding the controller mid-session and dropping whatever turn is in
   * flight. A resolver costs one call per request and no signature above it.
   */
  const baseUrl = (): string =>
    stringSetting(deps.settings, "baseUrl", "http://127.0.0.1:8765").replace(/\/+$/, "");
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
      // Called, not captured: the probe is what produces the "not answering"
      // warning the user is trying to clear, so probing the address they just
      // replaced reports a failure about a machine nobody is talking to.
      probe: () => probeHealth(deps.http, baseUrl()),
    },
  ];

  if (deps.createInProcess !== undefined) {
    const build = deps.createInProcess;
    choices.push({ id: ENGINE_PRAISONAI_TS, create: () => build(deps.persistence, deps.history) });
  }
  return choices;
}
