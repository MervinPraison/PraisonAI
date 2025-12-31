/**
 * DevTools - AI SDK v6 DevTools Integration
 * 
 * Provides optional DevTools integration for debugging AI SDK calls.
 * This is an optional dependency that provides visibility into LLM calls.
 */

// ============================================================================
// Types
// ============================================================================

export interface DevToolsConfig {
  /** Enable DevTools (default: auto-detect from NODE_ENV) */
  enabled?: boolean;
  /** DevTools server port (default: 3001) */
  port?: number;
  /** DevTools server host (default: localhost) */
  host?: string;
  /** Project name for DevTools UI */
  projectName?: string;
  /** Custom metadata to include */
  metadata?: Record<string, unknown>;
}

export interface DevToolsState {
  enabled: boolean;
  initialized: boolean;
  port?: number;
  host?: string;
}

// ============================================================================
// Global State
// ============================================================================

let devToolsState: DevToolsState = {
  enabled: false,
  initialized: false,
};

let devToolsInstance: unknown = null;

// ============================================================================
// DevTools Functions
// ============================================================================

/**
 * Enable AI SDK DevTools for debugging.
 * 
 * @example
 * ```typescript
 * // Enable in development
 * if (process.env.NODE_ENV === 'development') {
 *   await enableDevTools();
 * }
 * ```
 * 
 * @example With configuration
 * ```typescript
 * await enableDevTools({
 *   port: 3001,
 *   projectName: 'My AI App'
 * });
 * ```
 */
export async function enableDevTools(config?: DevToolsConfig): Promise<void> {
  if (devToolsState.initialized && devToolsState.enabled) {
    return; // Already enabled
  }

  // Check if we should enable
  const shouldEnable = config?.enabled ?? 
    (process.env.NODE_ENV === 'development' || process.env.PRAISONAI_DEVTOOLS === 'true');

  if (!shouldEnable) {
    return;
  }

  try {
    // Try to import @ai-sdk/devtools (optional dependency)
    // @ts-ignore - Optional dependency
    const devtools = await import('@ai-sdk/devtools');
    
    if ('enableDevTools' in devtools) {
      await (devtools as any).enableDevTools({
        port: config?.port,
        host: config?.host,
        projectName: config?.projectName,
        metadata: config?.metadata,
      });
      
      devToolsInstance = devtools;
      devToolsState = {
        enabled: true,
        initialized: true,
        port: config?.port || 3001,
        host: config?.host || 'localhost',
      };
      
      console.log(`🔧 AI SDK DevTools enabled at http://${devToolsState.host}:${devToolsState.port}`);
    }
  } catch (error: any) {
    if (error.code === 'ERR_MODULE_NOT_FOUND' || error.code === 'MODULE_NOT_FOUND') {
      console.warn(
        '⚠️  @ai-sdk/devtools not installed. Install with:\n' +
        '   npm install @ai-sdk/devtools\n' +
        '   or: pnpm add @ai-sdk/devtools'
      );
    } else {
      console.warn('⚠️  Failed to enable DevTools:', error.message);
    }
    
    devToolsState = {
      enabled: false,
      initialized: true,
    };
  }
}

/**
 * Disable DevTools.
 */
export async function disableDevTools(): Promise<void> {
  if (!devToolsState.enabled) {
    return;
  }

  try {
    if (devToolsInstance && typeof (devToolsInstance as any).disableDevTools === 'function') {
      await (devToolsInstance as any).disableDevTools();
    }
  } catch {
    // Ignore errors during disable
  }

  devToolsState = {
    enabled: false,
    initialized: true,
  };
  devToolsInstance = null;
}

/**
 * Check if DevTools is enabled.
 */
export function isDevToolsEnabled(): boolean {
  return devToolsState.enabled;
}

/**
 * Get DevTools state.
 */
export function getDevToolsState(): DevToolsState {
  return { ...devToolsState };
}

/**
 * Get DevTools URL.
 */
export function getDevToolsUrl(): string | null {
  if (!devToolsState.enabled) {
    return null;
  }
  return `http://${devToolsState.host || 'localhost'}:${devToolsState.port || 3001}`;
}

// ============================================================================
// Middleware for DevTools
// ============================================================================

/**
 * Create middleware that logs to DevTools.
 * 
 * @example
 * ```typescript
 * const model = wrapModel(openai('gpt-4o'), createDevToolsMiddleware());
 * ```
 */
export function createDevToolsMiddleware(): any {
  return {
    transformParams: async ({ params }: { params: any }) => {
      if (!devToolsState.enabled) {
        return params;
      }

      // Add DevTools metadata
      return {
        ...params,
        experimental_telemetry: {
          ...params.experimental_telemetry,
          isEnabled: true,
          metadata: {
            ...params.experimental_telemetry?.metadata,
            devtools: true,
          },
        },
      };
    },
  };
}

// ============================================================================
// Auto-enable in Development
// ============================================================================

/**
 * Auto-enable DevTools if in development mode.
 * Call this at app startup.
 */
export async function autoEnableDevTools(): Promise<void> {
  const isDev = process.env.NODE_ENV === 'development';
  const isExplicitlyEnabled = process.env.PRAISONAI_DEVTOOLS === 'true';
  const isExplicitlyDisabled = process.env.PRAISONAI_DEVTOOLS === 'false';

  if (isExplicitlyDisabled) {
    return;
  }

  if (isDev || isExplicitlyEnabled) {
    await enableDevTools();
  }
}
