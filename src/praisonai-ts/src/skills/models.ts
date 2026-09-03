/**
 * Skill enums and data models.
 *
 * Python parity with praisonaiagents/skills/models.py and
 * praisonaiagents/skills/capability_validator.py. String values are identical
 * to the Python Enum values so serialized state round-trips across runtimes.
 */

/**
 * Skill activation state based on requirement validation.
 *
 * Python: praisonaiagents/skills/models.py:19 `SkillState`.
 */
export enum SkillState {
  /** All requirements satisfied */
  ACTIVE = 'active',
  /** Some requirements missing (soft warn) */
  DEGRADED = 'degraded',
  /** Critical requirements missing (hard fail) */
  UNAVAILABLE = 'unavailable',
  /** Requirements not yet validated */
  UNKNOWN = 'unknown',
}

/**
 * Enforcement level for capability gates.
 *
 * Python: praisonaiagents/skills/capability_validator.py:19 `EnforcementLevel`.
 */
export enum EnforcementLevel {
  /** No enforcement (existing behavior) */
  DISABLED = 'disabled',
  /** Log only, no blocking */
  TELEMETRY = 'telemetry',
  /** Warning but allow activation */
  WARN = 'warn',
  /** Hard failure, block activation */
  STRICT = 'strict',
}
