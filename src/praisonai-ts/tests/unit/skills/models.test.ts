import { SkillState, EnforcementLevel } from '../../../src/skills';

// Values must equal the Python Enum values:
// praisonaiagents/skills/models.py:19 and capability_validator.py:19
describe('skills enums (Python parity)', () => {
  it('SkillState has the Python string values', () => {
    expect(SkillState.ACTIVE).toBe('active');
    expect(SkillState.DEGRADED).toBe('degraded');
    expect(SkillState.UNAVAILABLE).toBe('unavailable');
    expect(SkillState.UNKNOWN).toBe('unknown');
    expect(Object.values(SkillState)).toEqual(['active', 'degraded', 'unavailable', 'unknown']);
  });

  it('EnforcementLevel has the Python string values', () => {
    expect(EnforcementLevel.DISABLED).toBe('disabled');
    expect(EnforcementLevel.TELEMETRY).toBe('telemetry');
    expect(EnforcementLevel.WARN).toBe('warn');
    expect(EnforcementLevel.STRICT).toBe('strict');
    expect(Object.values(EnforcementLevel)).toEqual(['disabled', 'telemetry', 'warn', 'strict']);
  });
});
