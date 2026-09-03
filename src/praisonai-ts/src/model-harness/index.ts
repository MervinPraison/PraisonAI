/**
 * Model-family-aware agent harness.
 *
 * Port of `praisonaiagents/model_harness/__init__.py`. Selects, by model
 * id/family, a base/harness system-prompt fragment and a preferred file-edit
 * format (string-replace `edit_file` vs `apply_patch`).
 *
 * ```ts
 * import { resolveHarness } from 'praisonai/model-harness';
 * const profile = resolveHarness('claude-opus-4');
 * profile.basePrompt;           // optional prompt fragment (string or null)
 * profile.preferredEditFormat;  // "apply_patch" | "edit_file" | null
 * ```
 */
export {
  HarnessProfile,
  DEFAULT_PROFILE,
  registerProfile,
  resolveHarness,
  listHarnessProfiles,
  resetHarnessRegistry,
} from './profiles';
export type { HarnessProfileConfig, HarnessResolverProtocol, HarnessRegistryEntry } from './profiles';
