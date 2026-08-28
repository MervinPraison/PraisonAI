/**
 * The composition root. The one place that knows every concrete type.
 *
 * Every layer below takes its collaborators as parameters and names none of
 * them; the wiring happens here and nowhere else. That is what makes the two
 * seams real rather than aspirational -- swapping Tauri for React Native, or
 * praisonai-ts for another framework, is a different argument to this function
 * and no edit anywhere above it.
 *
 * `createApp` takes its adapters INJECTED rather than building them, so the
 * whole boot sequence runs under node:test against fakes. A composition root
 * that constructs its own dependencies is the one part of an app that can
 * never be tested, and it is also the part where ordering bugs live.
 */
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";
import type { ShellPort } from "../../core/src/ports/shell.ts";
import type { StoragePort } from "../../core/src/ports/storage.ts";
import type { SecretsPort } from "../../core/src/ports/secrets.ts";
import type { TimePort } from "../../core/src/ports/time.ts";
import { createSession, persistenceFor, type Session } from "../../core/src/chat/session.ts";
import {
  createSettingsStore,
  facadeFor,
  type SettingDef,
  type SettingsFacade,
  type SettingsStore,
} from "../../core/src/settings/store.ts";
import { createRunController, type RunController, type RunView } from "../../core/src/run/controller.ts";
import { attachBackGesture, createRouter, type Router } from "../../ui/src/router.ts";
import { selectEngine, type EngineChoice } from "./engines.ts";
import type { RunPersistence } from "../../engines/src/praisonai-ts/engine.ts";

export interface AppDeps {
  readonly storage: StoragePort;
  readonly secrets: SecretsPort;
  readonly time: TimePort;
  readonly shell: ShellPort;
  /**
   * Built FROM the session, not before it.
   *
   * A pre-built list was the bug: the session existed, the engine's
   * `persistence` port existed, and nothing connected them -- so `record()`
   * never ran in a real turn and no conversation was ever saved. Taking a
   * factory makes that impossible to express: there is no way to obtain the
   * engine list without being handed the thing engines write through.
   */
  readonly engines: (
    persistence: RunPersistence,
    settings: SettingsFacade,
  ) => readonly EngineChoice[];
  readonly settingDefs: readonly SettingDef[];
  /** Which engine to start with, normally read from settings. */
  /**
   * The engine to use when settings do not name one -- a first launch, or a
   * settings file that predates the key.
   *
   * NOT the engine to always use. It was exactly that, and `main.ts` passed a
   * string literal, so the engine the user selected in settings was stored,
   * displayed back to them, and ignored on every run.
   */
  readonly fallbackEngineId: string;
  readonly onPublish: (view: RunView) => void;
  /** Injected so boot is deterministic under test. */
  readonly now: () => number;
  readonly newChatId: () => string;
}

export interface App {
  readonly engine: AgentEnginePort;
  readonly controller: RunController;
  readonly session: Session;
  readonly settings: SettingsFacade;
  readonly router: Router;
  readonly shell: ShellPort;
  /** Tear down in reverse order of construction. Idempotent. */
  dispose(): Promise<void>;
}

export type BootResult =
  | { readonly ok: true; readonly app: App }
  | { readonly ok: false; readonly reason: string; readonly detail: string };

export async function createApp(deps: AppDeps): Promise<BootResult> {
  // 1. Settings first: the engine choice and its credentials come from here,
  //    so anything built before this would be built with defaults and rebuilt.
  const settingsStore: SettingsStore = createSettingsStore(deps.settingDefs, deps.storage, deps.secrets);
  await settingsStore.load();
  // 3. Everything above the seam. None of these can name a concrete adapter.
  // The session owns the join between the assistant-only TurnState and the
  // two-sided StoredChat, and it is what engines call to record a turn -- so
  // `end.userIndex` is produced by whatever actually did the write.
  const session = createSession({
    storage: deps.storage,
    engineId: deps.fallbackEngineId,
    now: deps.now,
    newChatId: deps.newChatId,
  });


  // 2. The engine, verified. A protocol mismatch stops the boot HERE, with a
  //    name, rather than mid-answer.
  //
  //    NOTE the ordering: the session is built above, because the in-process
  //    engine writes THROUGH it. `main.ts` builds the engine list from
  //    `enginesFor({ ..., persistence: session })`, so a turn recorded by the
  //    engine and a chat read by the UI are the same store.
  // The REAL facade, not a stub. The engine list is built from the settings
  // the user actually saved -- the base URL, the credentials, the choice of
  // engine. Building it from a stub meant every one of those was read from a
  // hardcoded default while the settings screen displayed the user's value.
  const settings = facadeFor(settingsStore, deps.secrets);

  // And the selection comes from settings too, falling back only when they do
  // not name one.
  const chosen = settings.get("engineId");
  const engineId = typeof chosen === "string" && chosen !== "" ? chosen : deps.fallbackEngineId;

  const selection = await selectEngine(engineId, deps.engines(persistenceFor(session), settings));
  if (!selection.ok) {
    return { ok: false, reason: selection.reason, detail: selection.detail };
  }
  const engine = selection.engine;

  const controller = createRunController({
    engine,
    time: deps.time,
    onPublish: deps.onPublish,
  });
  const router = createRouter({ name: "chats" });

  const subscriptions: Array<() => void> = [];

  // The router answers the OS back gesture. At the root it must answer false so
  // Android can exit -- a handler that always consumes traps the user in the app.
  subscriptions.push(attachBackGesture(deps.shell, router));

  // Backgrounding must stop the run loop and flush: on iOS the app can be
  // killed while suspended with no further callback, so anything unflushed at
  // this moment is simply gone.
  subscriptions.push(
    deps.shell.onLifecycleChanged((phase) => {
      if (phase === "background") void controller.stop();
    }),
  );

  let disposed = false;

  return {
    ok: true,
    app: {
      engine,
      controller,
      session,
      settings,
      router,
      shell: deps.shell,

      async dispose() {
        if (disposed) return; // idempotent
        disposed = true;
        // Unsubscribe BEFORE disposing the engine: a lifecycle event arriving
        // mid-teardown would otherwise call stop() on a disposed engine.
        for (const off of subscriptions.splice(0)) off();
        await controller.stop();
        await engine.dispose();
      },
    },
  };
}
