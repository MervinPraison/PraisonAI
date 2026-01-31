/**
 * Provider Registry - Extensible provider registration system
 * 
 * Fixes Issue #1095: Allows users to register custom providers
 * that can be resolved by name via createProvider().
 */

import type { LLMProvider, ProviderConfig } from './types';

/**
 * Provider constructor type
 */
export type ProviderConstructor = new (modelId: string, config?: ProviderConfig) => LLMProvider;

/**
 * Lazy loader function that returns a provider constructor
 * Used for tree-shaking and lazy loading of provider implementations
 */
export type ProviderLoader = () => ProviderConstructor;

/**
 * Options for registering a provider
 */
export interface RegisterOptions {
  /** Allow overwriting an existing registration */
  override?: boolean;
  /** Additional names that resolve to this provider */
  aliases?: string[];
}

/**
 * Internal entry in the registry
 */
interface RegistryEntry {
  /** The provider constructor or loader */
  provider: ProviderConstructor | ProviderLoader;
  /** Whether this is a loader function (vs direct constructor) */
  isLoader: boolean;
  /** Cached constructor if loaded from a loader */
  cachedConstructor?: ProviderConstructor;
  /** The canonical name (for aliases) */
  canonicalName: string;
}

/**
 * Provider Registry Interface
 */
export interface IProviderRegistry {
  register(name: string, provider: ProviderConstructor | ProviderLoader, options?: RegisterOptions): void;
  unregister(name: string): boolean;
  has(name: string): boolean;
  list(): string[];
  resolve(name: string, modelId: string, config?: ProviderConfig): LLMProvider;
  get(name: string): ProviderConstructor | ProviderLoader | undefined;
}

/**
 * Provider Registry Implementation
 * 
 * Manages registration and resolution of LLM providers by name.
 * Supports lazy loading, aliases, and isolated instances.
 */
export class ProviderRegistry implements IProviderRegistry {
  private entries: Map<string, RegistryEntry> = new Map();
  private aliases: Map<string, string> = new Map(); // alias -> canonical name

  /**
   * Register a provider by name
   * 
   * @param name - Provider name (e.g., 'cloudflare', 'ollama')
   * @param provider - Provider constructor or lazy loader function
   * @param options - Registration options
   * @throws Error if name is already registered (unless override: true)
   */
  register(
    name: string,
    provider: ProviderConstructor | ProviderLoader,
    options: RegisterOptions = {}
  ): void {
    const normalizedName = name.toLowerCase();
    
    // Check for existing registration
    if (this.entries.has(normalizedName) && !options.override) {
      throw new Error(
        `Provider '${name}' is already registered. ` +
        `Use { override: true } to replace it.`
      );
    }

    // Determine if this is a loader function or direct constructor
    const isLoader = this.isLoaderFunction(provider);

    const entry: RegistryEntry = {
      provider,
      isLoader,
      canonicalName: normalizedName,
    };

    this.entries.set(normalizedName, entry);

    // Register aliases
    if (options.aliases) {
      for (const alias of options.aliases) {
        const normalizedAlias = alias.toLowerCase();
        if (this.entries.has(normalizedAlias) && !options.override) {
          throw new Error(
            `Alias '${alias}' conflicts with existing provider. ` +
            `Use { override: true } to replace it.`
          );
        }
        this.aliases.set(normalizedAlias, normalizedName);
      }
    }
  }

  /**
   * Unregister a provider by name
   * 
   * @param name - Provider name to unregister
   * @returns true if provider was unregistered, false if not found
   */
  unregister(name: string): boolean {
    const normalizedName = name.toLowerCase();
    
    // Check if it's an alias
    if (this.aliases.has(normalizedName)) {
      this.aliases.delete(normalizedName);
      return true;
    }

    // Check if it's a canonical name
    if (this.entries.has(normalizedName)) {
      // Remove all aliases pointing to this provider
      for (const [alias, canonical] of this.aliases.entries()) {
        if (canonical === normalizedName) {
          this.aliases.delete(alias);
        }
      }
      this.entries.delete(normalizedName);
      return true;
    }

    return false;
  }

  /**
   * Check if a provider is registered
   * 
   * @param name - Provider name to check
   * @returns true if provider is registered
   */
  has(name: string): boolean {
    const normalizedName = name.toLowerCase();
    return this.entries.has(normalizedName) || this.aliases.has(normalizedName);
  }

  /**
   * List all registered provider names (canonical names only)
   * 
   * @returns Array of provider names
   */
  list(): string[] {
    return Array.from(this.entries.keys());
  }

  /**
   * List all names including aliases
   * 
   * @returns Array of all registered names and aliases
   */
  listAll(): string[] {
    return [...this.entries.keys(), ...this.aliases.keys()];
  }

  /**
   * Resolve a provider by name, creating an instance
   * 
   * @param name - Provider name
   * @param modelId - Model ID to pass to constructor
   * @param config - Optional provider config
   * @returns Provider instance
   * @throws Error if provider not found
   */
  resolve(name: string, modelId: string, config?: ProviderConfig): LLMProvider {
    const normalizedName = name.toLowerCase();
    
    // Resolve alias to canonical name
    const canonicalName = this.aliases.get(normalizedName) || normalizedName;
    
    const entry = this.entries.get(canonicalName);
    if (!entry) {
      const available = this.list();
      throw new Error(
        `Unknown provider: '${name}'. ` +
        `Available providers: ${available.length > 0 ? available.join(', ') : 'none'}. ` +
        `Register a custom provider with registerProvider('${name}', YourProviderClass).`
      );
    }

    // Get constructor (resolve loader if needed)
    const Constructor = this.getConstructor(entry);
    
    return new Constructor(modelId, config);
  }

  /**
   * Get the provider constructor/loader without instantiating
   * 
   * @param name - Provider name
   * @returns Provider constructor/loader or undefined
   */
  get(name: string): ProviderConstructor | ProviderLoader | undefined {
    const normalizedName = name.toLowerCase();
    const canonicalName = this.aliases.get(normalizedName) || normalizedName;
    return this.entries.get(canonicalName)?.provider;
  }

  /**
   * Get the resolved constructor for an entry
   */
  private getConstructor(entry: RegistryEntry): ProviderConstructor {
    if (!entry.isLoader) {
      return entry.provider as ProviderConstructor;
    }

    // Lazy load and cache
    if (!entry.cachedConstructor) {
      const loader = entry.provider as ProviderLoader;
      entry.cachedConstructor = loader();
    }

    return entry.cachedConstructor;
  }

  /**
   * Determine if a value is a loader function vs a constructor
   * Loaders are arrow functions or regular functions that return a class
   * Constructors have a prototype with constructor
   */
  private isLoaderFunction(value: ProviderConstructor | ProviderLoader): boolean {
    // Check if it's a class by looking at the string representation
    const str = value.toString();
    
    // Classes start with 'class ' in their toString
    if (str.startsWith('class ')) {
      return false;
    }
    
    // If it has a prototype with methods (more than just constructor), it's a class
    if (value.prototype && Object.getOwnPropertyNames(value.prototype).length > 1) {
      return false;
    }
    
    // Jest mock functions and arrow functions are loaders
    // They don't have a meaningful prototype or their prototype doesn't match class pattern
    if (typeof value === 'function') {
      // Arrow functions have no prototype or an empty prototype
      if (!value.prototype) {
        return true;
      }
      // Jest mocks have _isMockFunction property
      if ((value as any)._isMockFunction) {
        return true;
      }
      // Regular functions that aren't classes are loaders
      if (!str.startsWith('class ') && !str.startsWith('function ')) {
        return true;
      }
    }

    return false;
  }
}

// ============================================================================
// Default Registry Singleton
// ============================================================================

let defaultRegistry: ProviderRegistry | null = null;

/**
 * Get the default global provider registry
 * 
 * This is the registry used by createProvider() when no custom registry is specified.
 * Built-in providers (OpenAI, Anthropic, Google) are registered here.
 */
export function getDefaultRegistry(): ProviderRegistry {
  if (!defaultRegistry) {
    defaultRegistry = new ProviderRegistry();
    registerBuiltinProviders(defaultRegistry);
  }
  return defaultRegistry;
}

/**
 * Create a new isolated provider registry
 * 
 * Use this when you need a separate registry that doesn't share
 * registrations with the default global registry.
 */
export function createProviderRegistry(): ProviderRegistry {
  return new ProviderRegistry();
}

/**
 * Register a provider to the default global registry
 * 
 * @example
 * ```typescript
 * import { registerProvider } from 'praisonai';
 * import { CloudflareProvider } from './my-cloudflare-provider';
 * 
 * registerProvider('cloudflare', CloudflareProvider);
 * 
 * // Now works:
 * const agent = new Agent({ llm: 'cloudflare/workers-ai' });
 * ```
 */
export function registerProvider(
  name: string,
  provider: ProviderConstructor | ProviderLoader,
  options?: RegisterOptions
): void {
  getDefaultRegistry().register(name, provider, options);
}

/**
 * Unregister a provider from the default global registry
 */
export function unregisterProvider(name: string): boolean {
  return getDefaultRegistry().unregister(name);
}

/**
 * Check if a provider is registered in the default registry
 */
export function hasProvider(name: string): boolean {
  return getDefaultRegistry().has(name);
}

/**
 * List all providers in the default registry
 */
export function listProviders(): string[] {
  return getDefaultRegistry().list();
}

// ============================================================================
// Built-in Provider Registration
// ============================================================================

/**
 * Register built-in providers to a registry
 * Uses lazy loaders to avoid importing all providers at module load time
 */
export function registerBuiltinProviders(registry: ProviderRegistry): void {
  // OpenAI - lazy loaded
  registry.register('openai', () => {
    const { OpenAIProvider } = require('./openai');
    return OpenAIProvider;
  }, { aliases: ['oai'] });

  // Anthropic - lazy loaded
  registry.register('anthropic', () => {
    const { AnthropicProvider } = require('./anthropic');
    return AnthropicProvider;
  }, { aliases: ['claude'] });

  // Google - lazy loaded
  registry.register('google', () => {
    const { GoogleProvider } = require('./google');
    return GoogleProvider;
  }, { aliases: ['gemini'] });
}

/**
 * Reset the default registry (mainly for testing)
 * @internal
 */
export function _resetDefaultRegistry(): void {
  defaultRegistry = null;
}
