/**
 * Harness profiles and the model-family resolver.
 *
 * Port of `praisonaiagents/model_harness/profiles.py`.
 *
 * A {@link HarnessProfile} bundles two family-tuned knobs:
 *
 * - `basePrompt` — an optional system-prompt fragment prepended to the
 *   assembled prompt with family-specific tool-use guidance.
 * - `preferredEditFormat` — the file-edit primitive the family handles best
 *   (`"apply_patch"` or `"edit_file"`); `null` keeps the both-exposed
 *   behaviour.
 *
 * The registry maps case-insensitive substring matchers (evaluated against
 * the model id) to profiles. Unknown models fall back to
 * {@link DEFAULT_PROFILE}, which is behaviour-preserving (no prompt
 * fragment, no edit-format preference).
 *
 * Python's `threading.RLock` is omitted: the registry is a plain array on a
 * single-threaded runtime.
 */

/** Constructor options for {@link HarnessProfile} (Python dataclass fields). */
export interface HarnessProfileConfig {
  /** Identifier for the profile (e.g. `"default"`, `"anthropic"`). Default `"default"`. */
  name?: string;
  /** Optional prompt fragment prepended to the system prompt. `null` means none. */
  basePrompt?: string | null;
  /** Preferred edit primitive name, or `null` to keep exposing both primitives. */
  preferredEditFormat?: string | null;
}

/**
 * A model-family harness profile.
 *
 * Python parity: `model_harness/profiles.py::HarnessProfile` (frozen
 * dataclass). Instances are frozen after construction, matching
 * `@dataclass(frozen=True)`.
 */
export class HarnessProfile {
  readonly name: string;
  readonly basePrompt: string | null;
  readonly preferredEditFormat: string | null;

  constructor(config: HarnessProfileConfig = {}) {
    this.name = config.name ?? 'default';
    this.basePrompt = config.basePrompt ?? null;
    this.preferredEditFormat = config.preferredEditFormat ?? null;
    Object.freeze(this);
  }
}

/**
 * Protocol for objects that resolve a model id to a harness profile.
 *
 * Python parity: `model_harness/profiles.py::HarnessResolverProtocol`.
 */
export interface HarnessResolverProtocol {
  resolveHarness(model?: string | null): HarnessProfile;
}

/** Behaviour-preserving default: no fragment, no edit-format preference. */
export const DEFAULT_PROFILE: HarnessProfile = new HarnessProfile({ name: 'default' });

/** A registry entry: `[case-insensitive substrings, profile]`. First match wins. */
export type HarnessRegistryEntry = readonly [ReadonlyArray<string>, HarnessProfile];

/**
 * Family matchers. Ordered; first match wins. Kept intentionally small and
 * data-driven so consumers can extend/override via {@link registerProfile}.
 */
const _DEFAULT_REGISTRY: ReadonlyArray<HarnessRegistryEntry> = [
  [
    ['claude', 'anthropic'],
    new HarnessProfile({
      name: 'anthropic',
      basePrompt:
        'When editing files, prefer patch-style edits: use apply_patch ' +
        'to create or rewrite files and edit_file for targeted changes.',
      preferredEditFormat: 'apply_patch',
    }),
  ],
  [
    ['gpt', 'openai', 'o1', 'o3', 'o4'],
    new HarnessProfile({
      name: 'openai',
      basePrompt:
        'When editing files, prefer targeted string-replacement edits: ' +
        'use edit_file to modify existing files precisely.',
      preferredEditFormat: 'edit_file',
    }),
  ],
];

let _registry: HarnessRegistryEntry[] = [..._DEFAULT_REGISTRY];

/**
 * Register (prepend) a family matcher → profile mapping.
 *
 * New registrations take precedence over the built-in defaults so callers
 * can override behaviour.
 *
 * Python parity: `model_harness/profiles.py::register_profile`.
 *
 * @param matchers Case-insensitive substrings matched against the model id.
 *   Empty strings are dropped, as in Python; an entry with no matchers never
 *   matches.
 * @param profile The profile to resolve when a matcher hits.
 */
export function registerProfile(matchers: string[], profile: HarnessProfile): void {
  const normalized = matchers.filter((m) => Boolean(m)).map((m) => m.toLowerCase());
  _registry.unshift([normalized, profile]);
}

/**
 * Resolve a model id to a {@link HarnessProfile}.
 *
 * Unknown / falsy models return {@link DEFAULT_PROFILE} (no behaviour change).
 *
 * Python parity: `model_harness/profiles.py::resolve_harness`.
 */
export function resolveHarness(model?: string | null): HarnessProfile {
  if (!model) return DEFAULT_PROFILE;
  const lowered = model.toLowerCase();
  for (const [matchers, profile] of _registry) {
    if (matchers.some((m) => lowered.includes(m))) {
      return profile;
    }
  }
  return DEFAULT_PROFILE;
}

/** Snapshot of the current registry, most-recently-registered first (TypeScript-only). */
export function listHarnessProfiles(): ReadonlyArray<HarnessRegistryEntry> {
  return _registry.map(([matchers, profile]) => [[...matchers], profile] as const);
}

/**
 * Restore the built-in registry, discarding every {@link registerProfile}
 * call. TypeScript-only test helper; Python has no equivalent (its tests
 * patch the module-level list directly).
 */
export function resetHarnessRegistry(): void {
  _registry = [..._DEFAULT_REGISTRY];
}
