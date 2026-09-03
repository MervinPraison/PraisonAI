/**
 * Version utilities for the praisonai TypeScript package.
 *
 * Python parity: praisonaiagents/_version.py (`get_version`, `__version__`).
 * Python reads `pyproject.toml`; this module reads `package.json` so each
 * package keeps a single source of truth for its version. The value is read
 * once at import time and cached, exactly like `__version__` in Python.
 *
 * Resolution order (both work from `dist/` (CJS) and `dist/esm/`, because
 * scripts/esm-shim.js repoints relative `require()` calls in the ESM build at
 * the mirrored CommonJS location and supplies `__dirname`):
 *   1. `require('../package.json')` — src/version.ts and dist/version.js both
 *      sit one level below the package root.
 *   2. Walk up from `__dirname` looking for a package.json named `praisonai`.
 *   3. `"unknown"`, with a runtime warning — Python warns RuntimeWarning and
 *      returns "unknown" rather than breaking the import.
 */

import * as fs from 'fs';
import * as path from 'path';

const PACKAGE_NAME = 'praisonai';
const UNKNOWN_VERSION = 'unknown';

function versionFromRequire(): string | undefined {
    try {
        const pkg = require('../package.json') as { name?: string; version?: string };
        if (pkg && typeof pkg.version === 'string' && pkg.version) {
            return pkg.version;
        }
    } catch {
        // Not resolvable from here (bundled, relocated, or no CommonJS require).
    }
    return undefined;
}

function versionFromFilesystem(): string | undefined {
    if (typeof __dirname !== 'string' || !__dirname) {
        return undefined;
    }
    let dir = __dirname;
    // src/ or dist/ -> root is one up; dist/esm/ -> two up. Three keeps a margin.
    for (let depth = 0; depth < 3; depth++) {
        const candidate = path.join(dir, '..', 'package.json');
        try {
            if (fs.existsSync(candidate)) {
                const pkg = JSON.parse(fs.readFileSync(candidate, 'utf8')) as { name?: string; version?: string };
                if (pkg && pkg.name === PACKAGE_NAME && typeof pkg.version === 'string' && pkg.version) {
                    return pkg.version;
                }
            }
        } catch {
            // Unreadable or malformed: keep walking up.
        }
        dir = path.join(dir, '..');
    }
    return undefined;
}

/**
 * Read the package version from package.json.
 *
 * Python parity: `praisonaiagents._version.get_version()`. Never throws: on
 * failure it warns (when `process.emitWarning` exists) and returns "unknown",
 * matching the Python fallback.
 */
export function getVersion(): string {
    const version = versionFromRequire() ?? versionFromFilesystem();
    if (version) {
        return version;
    }
    if (typeof process !== 'undefined' && typeof process.emitWarning === 'function') {
        process.emitWarning(
            `Failed to read version from package.json. Using '${UNKNOWN_VERSION}'.`,
            'RuntimeWarning'
        );
    }
    return UNKNOWN_VERSION;
}

/** The package version, read once at import time. Python parity: `__version__`. */
export const VERSION: string = getVersion();

/** Python-spelled alias of {@link VERSION} (`praisonaiagents.__version__`). */
export const __version__: string = VERSION;
