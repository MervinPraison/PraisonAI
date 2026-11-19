/**
 * The one bind guard every TS network server calls before `listen()`.
 * Mirrors Python's `praisonaiagents.agent.launch_security.require_bind_token`.
 */
// No static Node builtin imports: os/config.ts is reachable from webview bundles.

/** True for localhost, ::1 and the whole 127.0.0.0/8 range. */
export function isLoopbackHost(host: string): boolean {
    const h = host.trim().toLowerCase().replace(/^\[|\]$/g, '');
    if (h === 'localhost' || h === '::1' || h === '0:0:0:0:0:0:0:1') return true;
    const v4 = h.startsWith('::ffff:') ? h.slice(7) : h;
    return /^127(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/.test(v4);
}

/** Loopback may run keyless; a non-loopback host without a token throws. */
export function requireBindToken(
    host: string,
    token: string | undefined | null,
    opts: { server: string; hint: string },
): void {
    if (token || isLoopbackHost(host)) return;
    throw new Error(
        `${opts.server} refuses to bind non-loopback host '${host}' without an auth token. ` +
        `${opts.hint}, or bind to 127.0.0.1.`,
    );
}

/** Constant-time token check; a missing or empty value never matches. */
export function tokenMatches(supplied: unknown, expected: string | undefined | null): boolean {
    if (typeof supplied !== 'string' || !supplied || !expected) return false;
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { createHash, timingSafeEqual } = require('crypto');
    const digest = (v: string) => createHash('sha256').update(v, 'utf8').digest();
    return timingSafeEqual(digest(supplied), digest(expected));
}
