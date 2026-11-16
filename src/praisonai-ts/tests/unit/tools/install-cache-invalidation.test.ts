import { describe, expect, it } from '@jest/globals';
import { ToolsRegistry } from '../../../src/tools/registry/registry';
import type { ToolMetadata } from '../../../src/tools/registry/types';

const missingPackage = '@praisonai-test/not-installed-registry-fixture';
function register(registry: ToolsRegistry, packageName: string) {
  const metadata: ToolMetadata = {
    id: 'dependency-test', displayName: 'Dependency test', description: 'Local status test',
    tags: [], requiredEnv: [], optionalEnv: [], docsSlug: 'tools/dependency-test',
    install: { npm: `npm install ${packageName}`, pnpm: '', yarn: '', bun: '' },
    capabilities: {}, packageName,
  };
  registry.register(metadata, () => ({
    name: 'dependency-test', description: 'Local status test',
    parameters: { type: 'object', properties: {} }, execute: async () => 'ok',
  }));
}

describe('ToolsRegistry installation cache lifecycle', () => {
  it('does not report a removed cached tool as installed', async () => {
    const registry = new ToolsRegistry();
    register(registry, 'node:path');
    expect(await registry.checkInstalled('dependency-test')).toBe(true);
    expect(registry.unregister('dependency-test')).toBe(true);
    expect(await registry.checkInstalled('dependency-test')).toBe(false);
    expect(await registry.getInstallStatus('dependency-test')).toBeNull();
  });

  it('rechecks an installed dependency replaced by a missing one', async () => {
    const registry = new ToolsRegistry();
    register(registry, 'node:path');
    expect(await registry.checkInstalled('dependency-test')).toBe(true);
    register(registry, missingPackage);
    expect(await registry.getInstallStatus('dependency-test')).toMatchObject({
      installed: false, installCommand: `npm install ${missingPackage}`,
    });
  });

  it('rechecks a missing dependency replaced by an installed one', async () => {
    const registry = new ToolsRegistry();
    register(registry, missingPackage);
    expect(await registry.checkInstalled('dependency-test')).toBe(false);
    register(registry, 'node:path');
    expect(await registry.getInstallStatus('dependency-test')).toMatchObject({ installed: true, installCommand: undefined });
  });

  it('does not cache an old successful import after replacement', async () => {
    const registry = new ToolsRegistry();
    register(registry, 'node:path');
    const oldCheck = registry.checkInstalled('dependency-test');
    register(registry, missingPackage);
    expect(await oldCheck).toBe(true);
    expect(await registry.checkInstalled('dependency-test')).toBe(false);
  });

  it('does not cache an old failed import after replacement', async () => {
    const registry = new ToolsRegistry();
    register(registry, missingPackage);
    const oldCheck = registry.checkInstalled('dependency-test');
    register(registry, 'node:path');
    expect(await oldCheck).toBe(false);
    expect(await registry.checkInstalled('dependency-test')).toBe(true);
  });

  it('reports an unknown tool as unavailable', async () => {
    const registry = new ToolsRegistry();
    expect(await registry.checkInstalled('unknown')).toBe(false);
    expect(await registry.getInstallStatus('unknown')).toBeNull();
  });

  it('keeps repeated installed checks consistent', async () => {
    const registry = new ToolsRegistry();
    register(registry, 'node:path');
    expect(await registry.checkInstalled('dependency-test')).toBe(true);
    expect(await registry.checkInstalled('dependency-test')).toBe(true);
  });

  it('keeps repeated missing checks consistent', async () => {
    const registry = new ToolsRegistry();
    register(registry, missingPackage);
    expect(await registry.checkInstalled('dependency-test')).toBe(false);
    expect(await registry.checkInstalled('dependency-test')).toBe(false);
  });
});
