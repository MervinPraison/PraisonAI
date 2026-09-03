/**
 * Parity notices for options accepted from the Python SDK surface.
 *
 * The signature parity gate (src/praisonai/praisonai/_dev/parity/signatures)
 * requires every Python constructor/method parameter to exist on the
 * TypeScript side. Some of those parameters are accepted and typed before the
 * behaviour behind them is ported. Such an option must never be silently
 * ignored: a setting that is accepted and does nothing is a defect that no
 * test catches. This helper makes the gap audible once per process and
 * queryable from code.
 *
 * Usage inside a constructor:
 *
 *   if (config.sandbox !== undefined) notYetHonoured('Agent', 'sandbox');
 *
 * Silence with PRAISONAI_PARITY_SILENT=1 (for example in tests), and read
 * back what was accepted-but-unhonoured with `unhonouredOptions()`.
 */

const seen = new Set<string>();

function silenced(): boolean {
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return env?.PRAISONAI_PARITY_SILENT === '1' || env?.PRAISONAI_PARITY_SILENT === 'true';
}

/**
 * Record that `option` on `surface` was supplied by the caller but is not yet
 * honoured by the TypeScript implementation. Warns once per (surface, option).
 */
export function notYetHonoured(surface: string, option: string, detail?: string): void {
  const key = `${surface}.${option}`;
  if (seen.has(key)) return;
  seen.add(key);
  if (silenced()) return;
  const extra = detail ? ` ${detail}` : '';
  console.warn(
    `[praisonai] ${surface}: option "${option}" is accepted for parity with the Python SDK but is not yet honoured in TypeScript.${extra}`
  );
}

/** Every (surface, option) pair reported so far, as "Surface.option" keys. */
export function unhonouredOptions(): string[] {
  return Array.from(seen).sort();
}

/** Test helper: forget previously reported keys so warnings fire again. */
export function resetParityNotices(): void {
  seen.clear();
}
