/**
 * src/version.ts — Python parity: praisonaiagents/_version.py
 */
import * as fs from 'fs';
import * as path from 'path';
import { VERSION, __version__, getVersion } from '../../../src/version';

describe('version (parity: _version.py)', () => {
    const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../package.json'), 'utf8'));

    it('__version__ equals package.json version', () => {
        expect(__version__).toBe(pkg.version);
    });

    it('VERSION equals package.json version and is the same string as __version__', () => {
        expect(VERSION).toBe(pkg.version);
        expect(VERSION).toBe(__version__);
    });

    it('getVersion() re-reads the same value and looks like semver', () => {
        expect(getVersion()).toBe(pkg.version);
        expect(getVersion()).toMatch(/^\d+\.\d+\.\d+/);
        expect(getVersion()).not.toBe('unknown');
    });
});
