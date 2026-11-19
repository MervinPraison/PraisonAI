/**
 * Environment for a child process that runs a model-chosen command or code.
 *
 * Only non-secret basics are inherited from the host (path, locale, temp dir,
 * shell and user identity, and the Windows system variables a process needs to
 * start). Operators who need another host variable inside such a command name
 * it in `PRAISONAI_SHELL_ENV_ALLOWLIST` (comma-separated), the same knob the
 * Python SDK reads. Variables passed explicitly by the caller always win.
 */

const BASE_NAMES = new Set([
  'PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LANGUAGE', 'TERM',
  'TMPDIR', 'TMP', 'TEMP', 'TZ',
  // Windows
  'SYSTEMROOT', 'SYSTEMDRIVE', 'COMSPEC', 'PATHEXT', 'WINDIR', 'USERPROFILE',
  'APPDATA', 'LOCALAPPDATA',
]);

export function buildChildEnv(
  explicit?: Record<string, string | undefined>,
  source: Record<string, string | undefined> = typeof process !== 'undefined' ? process.env : {},
): Record<string, string> {
  const extra = new Set(
    (source.PRAISONAI_SHELL_ENV_ALLOWLIST ?? '')
      .split(',')
      .map((name) => name.trim().toUpperCase())
      .filter(Boolean),
  );
  const env: Record<string, string> = {};
  for (const [name, value] of Object.entries(source)) {
    if (value === undefined) continue;
    // Upper-cased so Windows spellings such as `Path` and `ComSpec` match.
    const upper = name.toUpperCase();
    if (BASE_NAMES.has(upper) || upper.startsWith('LC_') || extra.has(upper)) env[name] = value;
  }
  for (const [name, value] of Object.entries(explicit ?? {})) {
    if (value !== undefined) env[name] = value;
  }
  return env;
}
