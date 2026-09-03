/**
 * Runtime execution protocols and registry for PraisonAI agents.
 *
 * Port of the protocol and registry parts of `praisonaiagents/runtime/`
 * (`protocols.py`, `registry.py`, `builtin.py`). Turn contexts,
 * capabilities, middleware, doctor rules, health checks and the run journal
 * are not yet ported.
 */
export {
  RuntimeConfig,
  RuntimeResult,
  RuntimeDelta,
  isAgentRuntime,
} from './protocols';
export type {
  RuntimeMode,
  TurnRuntimeProtocol,
  TurnContextBuilderProtocol,
  RuntimeConfigInit,
  RuntimeResultInit,
  RuntimeDeltaInit,
  RuntimeDeltaType,
  RuntimeCapabilityMatrix,
  RunTurnOptions,
  AgentRuntimeProtocol,
} from './protocols';

export {
  RuntimeRegistryEntry,
  RuntimeRegistryError,
  RuntimeRegistry,
  PraisonAIRuntime,
  getRuntimeRegistry,
  registerRuntime,
  unregisterRuntime,
  listRuntimes,
  resolveRuntime,
  addRuntimeAlias,
  isRuntimeAvailable,
} from './registry';
export type {
  RuntimeRegistryEntryInit,
  RuntimeFactory,
  RuntimeRegistryProtocol,
  RuntimeAgentLike,
  PraisonAIRuntimeOptions,
} from './registry';
