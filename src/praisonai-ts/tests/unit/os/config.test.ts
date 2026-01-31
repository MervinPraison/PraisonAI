/**
 * Unit tests for AgentOS config
 */

import {
    AgentOSConfig,
    AgentAppConfig,
    DEFAULT_AGENTOS_CONFIG,
    mergeConfig
} from '../../../src/os/config';

describe('AgentOSConfig', () => {
    describe('DEFAULT_AGENTOS_CONFIG', () => {
        it('should have correct default values', () => {
            expect(DEFAULT_AGENTOS_CONFIG.name).toBe('PraisonAI App');
            expect(DEFAULT_AGENTOS_CONFIG.host).toBe('0.0.0.0');
            expect(DEFAULT_AGENTOS_CONFIG.port).toBe(8000);
            expect(DEFAULT_AGENTOS_CONFIG.reload).toBe(false);
            expect(DEFAULT_AGENTOS_CONFIG.corsOrigins).toEqual(['*']);
            expect(DEFAULT_AGENTOS_CONFIG.apiPrefix).toBe('/api');
            expect(DEFAULT_AGENTOS_CONFIG.docsUrl).toBe('/docs');
            expect(DEFAULT_AGENTOS_CONFIG.openapiUrl).toBe('/openapi.json');
            expect(DEFAULT_AGENTOS_CONFIG.debug).toBe(false);
            expect(DEFAULT_AGENTOS_CONFIG.logLevel).toBe('info');
            expect(DEFAULT_AGENTOS_CONFIG.workers).toBe(1);
            expect(DEFAULT_AGENTOS_CONFIG.timeout).toBe(60);
            expect(DEFAULT_AGENTOS_CONFIG.metadata).toEqual({});
        });
    });

    describe('mergeConfig', () => {
        it('should return defaults when no config provided', () => {
            const result = mergeConfig();
            expect(result).toEqual(DEFAULT_AGENTOS_CONFIG);
        });

        it('should merge user config with defaults', () => {
            const userConfig: AgentOSConfig = {
                name: 'My App',
                port: 9000,
                debug: true,
            };

            const result = mergeConfig(userConfig);

            expect(result.name).toBe('My App');
            expect(result.port).toBe(9000);
            expect(result.debug).toBe(true);
            // Defaults preserved
            expect(result.host).toBe('0.0.0.0');
            expect(result.corsOrigins).toEqual(['*']);
        });

        it('should merge metadata objects', () => {
            const userConfig: AgentOSConfig = {
                metadata: { key: 'value' },
            };

            const result = mergeConfig(userConfig);

            expect(result.metadata).toEqual({ key: 'value' });
        });

        it('should handle all log levels', () => {
            const levels = ['debug', 'info', 'warn', 'error'] as const;

            for (const level of levels) {
                const result = mergeConfig({ logLevel: level });
                expect(result.logLevel).toBe(level);
            }
        });
    });

    describe('AgentAppConfig alias', () => {
        it('should be exactly the same type as AgentOSConfig', () => {
            // Type check: AgentAppConfig should accept AgentOSConfig values
            const config: AgentAppConfig = {
                name: 'Test',
                port: 3000,
            };

            // This is a type-level test; if it compiles, the alias works
            expect(config.name).toBe('Test');
        });
    });
});
