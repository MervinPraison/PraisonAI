/**
 * Plugin Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents/plugins module
 * 
 * Provides:
 * - Plugin protocols and interfaces
 * - Plugin manager for discovery and loading
 * - Plugin hooks and lifecycle
 * - Single-file plugin support
 */

// ============================================================================
// Plugin Hooks Enum
// ============================================================================

/**
 * Plugin hook points.
 * Python parity: praisonaiagents/plugins/plugin.py
 */
export enum PluginHook {
  BEFORE_AGENT = 'before_agent',
  AFTER_AGENT = 'after_agent',
  BEFORE_TOOL = 'before_tool',
  AFTER_TOOL = 'after_tool',
  BEFORE_LLM = 'before_llm',
  AFTER_LLM = 'after_llm',
  ON_ERROR = 'on_error',
  ON_START = 'on_start',
  ON_STOP = 'on_stop',
}

/**
 * Plugin types.
 * Python parity: praisonaiagents/plugins/plugin.py
 */
export enum PluginType {
  TOOL = 'tool',
  HOOK = 'hook',
  AGENT = 'agent',
  LLM = 'llm',
  MEMORY = 'memory',
  FUNCTION = 'function',
}

// ============================================================================
// Plugin Interfaces
// ============================================================================

/**
 * Plugin metadata.
 * Python parity: praisonaiagents/plugins/parser.py
 */
export interface PluginMetadata {
  name: string;
  version: string;
  description?: string;
  author?: string;
  hooks?: PluginHook[];
  type?: PluginType;
  dependencies?: string[];
  config?: Record<string, any>;
}

/**
 * Plugin info for listing.
 * Python parity: praisonaiagents/plugins/plugin.py
 */
export interface PluginInfo {
  name: string;
  version: string;
  description?: string;
  enabled: boolean;
  type: PluginType | string;
  hooks?: PluginHook[];
}

/**
 * Plugin protocol interface.
 * Python parity: praisonaiagents/plugins/protocols.py
 */
export interface PluginProtocol {
  name: string;
  version: string;
  description?: string;
  hooks?: PluginHook[];
  
  initialize?(): void | Promise<void>;
  shutdown?(): void | Promise<void>;
  onHook?(hook: PluginHook, ...args: any[]): any | Promise<any>;
}

/**
 * Tool plugin protocol.
 * Python parity: praisonaiagents/plugins/protocols.py
 */
export interface ToolPluginProtocol extends PluginProtocol {
  type: 'tool';
  execute(input: any): any | Promise<any>;
  getSchema(): Record<string, any>;
}

/**
 * Hook plugin protocol.
 * Python parity: praisonaiagents/plugins/protocols.py
 */
export interface HookPluginProtocol extends PluginProtocol {
  type: 'hook';
  hooks: PluginHook[];
  handle(hook: PluginHook, context: any): any | Promise<any>;
}

/**
 * Agent plugin protocol.
 * Python parity: praisonaiagents/plugins/protocols.py
 */
export interface AgentPluginProtocol extends PluginProtocol {
  type: 'agent';
  beforeAgent?(agentName: string, input: string): string | Promise<string>;
  afterAgent?(agentName: string, output: string): string | Promise<string>;
}

/**
 * LLM plugin protocol.
 * Python parity: praisonaiagents/plugins/protocols.py
 */
export interface LLMPluginProtocol extends PluginProtocol {
  type: 'llm';
  beforeLLM?(messages: any[], options: any): any | Promise<any>;
  afterLLM?(response: any): any | Promise<any>;
}

// ============================================================================
// Plugin Class
// ============================================================================

/**
 * Base Plugin class.
 * Python parity: praisonaiagents/plugins/plugin.py
 */
export class Plugin implements PluginProtocol {
  name: string;
  version: string;
  description?: string;
  hooks: PluginHook[];
  type: PluginType;
  private _enabled: boolean = false;

  constructor(config: {
    name: string;
    version?: string;
    description?: string;
    hooks?: PluginHook[];
    type?: PluginType;
  }) {
    this.name = config.name;
    this.version = config.version ?? '1.0.0';
    this.description = config.description;
    this.hooks = config.hooks ?? [];
    this.type = config.type ?? PluginType.FUNCTION;
  }

  get enabled(): boolean {
    return this._enabled;
  }

  enable(): void {
    this._enabled = true;
  }

  disable(): void {
    this._enabled = false;
  }

  initialize(): void | Promise<void> {
    // Override in subclass
  }

  shutdown(): void | Promise<void> {
    // Override in subclass
  }

  onHook(hook: PluginHook, ...args: any[]): any | Promise<any> {
    // Override in subclass
    return args[0];
  }

  getInfo(): PluginInfo {
    return {
      name: this.name,
      version: this.version,
      description: this.description,
      enabled: this._enabled,
      type: this.type,
      hooks: this.hooks,
    };
  }
}

/**
 * Function-based plugin.
 * Python parity: praisonaiagents/plugins/plugin.py
 */
export class FunctionPlugin extends Plugin {
  private _handler: (hook: PluginHook, ...args: any[]) => any;

  constructor(config: {
    name: string;
    version?: string;
    description?: string;
    hooks?: PluginHook[];
    handler: (hook: PluginHook, ...args: any[]) => any;
  }) {
    super({
      name: config.name,
      version: config.version,
      description: config.description,
      hooks: config.hooks,
      type: PluginType.FUNCTION,
    });
    this._handler = config.handler;
  }

  onHook(hook: PluginHook, ...args: any[]): any {
    if (this.hooks.includes(hook)) {
      return this._handler(hook, ...args);
    }
    return args[0];
  }
}

// ============================================================================
// Plugin Parse Error
// ============================================================================

/**
 * Plugin parse error.
 * Python parity: praisonaiagents/plugins/parser.py
 */
export class PluginParseError extends Error {
  constructor(
    message: string,
    public readonly filePath?: string,
    public readonly line?: number
  ) {
    super(message);
    this.name = 'PluginParseError';
  }
}

// ============================================================================
// Plugin Manager
// ============================================================================

/**
 * Plugin manager for discovery and lifecycle.
 * Python parity: praisonaiagents/plugins/manager.py
 */
export class PluginManager {
  private _plugins: Map<string, Plugin> = new Map();
  private _singleFilePlugins: Map<string, PluginMetadata> = new Map();
  private _hookHandlers: Map<PluginHook, Array<(args: any[]) => any>> = new Map();

  constructor() {
    // Initialize hook handler maps
    for (const hook of Object.values(PluginHook)) {
      this._hookHandlers.set(hook, []);
    }
  }

  /**
   * Register a plugin.
   */
  register(plugin: Plugin): void {
    this._plugins.set(plugin.name, plugin);
    
    // Register hook handlers
    for (const hook of plugin.hooks) {
      const handlers = this._hookHandlers.get(hook) ?? [];
      handlers.push((...args: any[]) => plugin.onHook(hook, ...args));
      this._hookHandlers.set(hook, handlers);
    }
  }

  /**
   * Unregister a plugin.
   */
  unregister(name: string): boolean {
    const plugin = this._plugins.get(name);
    if (plugin) {
      plugin.disable();
      this._plugins.delete(name);
      return true;
    }
    return false;
  }

  /**
   * Get a plugin by name.
   */
  get(name: string): Plugin | undefined {
    return this._plugins.get(name);
  }

  /**
   * Enable a plugin.
   */
  enable(name: string): boolean {
    const plugin = this._plugins.get(name);
    if (plugin) {
      plugin.enable();
      return true;
    }
    return false;
  }

  /**
   * Disable a plugin.
   */
  disable(name: string): boolean {
    const plugin = this._plugins.get(name);
    if (plugin) {
      plugin.disable();
      return true;
    }
    return false;
  }

  /**
   * Check if a plugin is enabled.
   */
  isEnabled(name: string): boolean {
    const plugin = this._plugins.get(name);
    return plugin?.enabled ?? false;
  }

  /**
   * List all plugins.
   */
  listPlugins(): PluginInfo[] {
    const result: PluginInfo[] = [];
    
    for (const plugin of this._plugins.values()) {
      result.push(plugin.getInfo());
    }
    
    for (const [name, meta] of this._singleFilePlugins) {
      result.push({
        name,
        version: meta.version,
        description: meta.description,
        enabled: false,
        type: meta.type ?? 'single_file',
        hooks: meta.hooks,
      });
    }
    
    return result;
  }

  /**
   * Fire a hook to all registered handlers.
   */
  async fireHook(hook: PluginHook, ...args: any[]): Promise<any> {
    const handlers = this._hookHandlers.get(hook) ?? [];
    let result = args[0];
    
    for (const handler of handlers) {
      const handlerResult = await handler(args);
      if (handlerResult !== undefined) {
        result = handlerResult;
      }
    }
    
    return result;
  }

  /**
   * Fire a hook synchronously.
   */
  fireHookSync(hook: PluginHook, ...args: any[]): any {
    const handlers = this._hookHandlers.get(hook) ?? [];
    let result = args[0];
    
    for (const handler of handlers) {
      const handlerResult = handler(args);
      if (handlerResult !== undefined) {
        result = handlerResult;
      }
    }
    
    return result;
  }

  /**
   * Initialize all plugins.
   */
  async initializeAll(): Promise<void> {
    for (const plugin of this._plugins.values()) {
      if (plugin.enabled && plugin.initialize) {
        await plugin.initialize();
      }
    }
  }

  /**
   * Shutdown all plugins.
   */
  async shutdownAll(): Promise<void> {
    for (const plugin of this._plugins.values()) {
      if (plugin.enabled && plugin.shutdown) {
        await plugin.shutdown();
      }
    }
  }

  /**
   * Auto-discover plugins from default directories.
   */
  autoDiscoverPlugins(): void {
    // In browser/Node.js, this would scan directories
    // For now, this is a no-op placeholder
  }

  /**
   * Load plugins from a directory.
   */
  loadFromDirectory(path: string): void {
    // Placeholder for directory loading
    // Would use fs in Node.js environment
  }
}

// ============================================================================
// Global Plugin Manager
// ============================================================================

let _globalPluginManager: PluginManager | null = null;

/**
 * Get the global plugin manager.
 * Python parity: praisonaiagents/plugins/manager.py
 */
export function getPluginManager(): PluginManager {
  if (!_globalPluginManager) {
    _globalPluginManager = new PluginManager();
  }
  return _globalPluginManager;
}

// ============================================================================
// Plugin Discovery Functions
// ============================================================================

/**
 * Get default plugin directories.
 * Python parity: praisonaiagents/plugins/discovery.py
 */
export function getDefaultPluginDirs(): string[] {
  const dirs: string[] = [];
  
  // Project-level
  dirs.push('./.praison/plugins');
  dirs.push('./.praisonai/plugins');
  
  // User-level (would use os.homedir() in Node.js)
  if (typeof process !== 'undefined' && process.env?.HOME) {
    dirs.push(`${process.env.HOME}/.praison/plugins`);
    dirs.push(`${process.env.HOME}/.praisonai/plugins`);
  }
  
  return dirs;
}

/**
 * Ensure plugin directory exists.
 * Python parity: praisonaiagents/plugins/discovery.py
 */
export function ensurePluginDir(path: string): boolean {
  // In Node.js, would use fs.mkdirSync
  // For browser, this is a no-op
  return true;
}

/**
 * Discover plugins in a directory.
 * Python parity: praisonaiagents/plugins/discovery.py
 */
export function discoverPlugins(directory: string): PluginMetadata[] {
  // Placeholder - would scan directory for plugin files
  return [];
}

/**
 * Load a single plugin.
 * Python parity: praisonaiagents/plugins/discovery.py
 */
export function loadPlugin(path: string): Plugin | null {
  // Placeholder - would load and instantiate plugin
  return null;
}

/**
 * Discover and load all plugins.
 * Python parity: praisonaiagents/plugins/discovery.py
 */
export function discoverAndLoadPlugins(directories?: string[]): Plugin[] {
  const dirs = directories ?? getDefaultPluginDirs();
  const plugins: Plugin[] = [];
  
  for (const dir of dirs) {
    const discovered = discoverPlugins(dir);
    for (const meta of discovered) {
      const plugin = new Plugin({
        name: meta.name,
        version: meta.version,
        description: meta.description,
        hooks: meta.hooks,
        type: meta.type,
      });
      plugins.push(plugin);
    }
  }
  
  return plugins;
}

/**
 * Get plugin template.
 * Python parity: praisonaiagents/plugins/discovery.py
 */
export function getPluginTemplate(name: string): string {
  return `/**
 * ${name} Plugin
 * 
 * A PraisonAI plugin.
 */

import { Plugin, PluginHook, PluginType } from 'praisonai';

export class ${name}Plugin extends Plugin {
  constructor() {
    super({
      name: '${name.toLowerCase()}',
      version: '1.0.0',
      description: 'A custom plugin',
      hooks: [PluginHook.BEFORE_AGENT],
      type: PluginType.HOOK,
    });
  }

  onHook(hook: PluginHook, ...args: any[]): any {
    if (hook === PluginHook.BEFORE_AGENT) {
      console.log('Before agent:', args);
    }
    return args[0];
  }
}

export default new ${name}Plugin();
`;
}

// ============================================================================
// Plugin Parser Functions
// ============================================================================

/**
 * Parse plugin header from content.
 * Python parity: praisonaiagents/plugins/parser.py
 */
export function parsePluginHeader(content: string): PluginMetadata | null {
  // Look for YAML frontmatter or JSDoc-style header
  const yamlMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (yamlMatch) {
    try {
      // Simple YAML parsing for common fields
      const yaml = yamlMatch[1];
      const metadata: PluginMetadata = {
        name: '',
        version: '1.0.0',
      };
      
      const nameMatch = yaml.match(/name:\s*(.+)/);
      if (nameMatch) metadata.name = nameMatch[1].trim();
      
      const versionMatch = yaml.match(/version:\s*(.+)/);
      if (versionMatch) metadata.version = versionMatch[1].trim();
      
      const descMatch = yaml.match(/description:\s*(.+)/);
      if (descMatch) metadata.description = descMatch[1].trim();
      
      const authorMatch = yaml.match(/author:\s*(.+)/);
      if (authorMatch) metadata.author = authorMatch[1].trim();
      
      return metadata;
    } catch {
      return null;
    }
  }
  
  // Look for JSDoc-style @plugin annotation
  const jsdocMatch = content.match(/@plugin\s+(\w+)/);
  if (jsdocMatch) {
    return {
      name: jsdocMatch[1],
      version: '1.0.0',
    };
  }
  
  return null;
}

/**
 * Parse plugin header from file path.
 * Python parity: praisonaiagents/plugins/parser.py
 */
export function parsePluginHeaderFromFile(filePath: string): PluginMetadata | null {
  // In Node.js, would read file and call parsePluginHeader
  // For browser, this is a placeholder
  return null;
}

// ============================================================================
// Easy Enable API
// ============================================================================

let _pluginsEnabled = false;
let _enabledPluginNames: string[] | null = null;

/**
 * Enable the plugin system.
 * Python parity: praisonaiagents/plugins/__init__.py
 */
export function enable(plugins?: string[]): void {
  _pluginsEnabled = true;
  _enabledPluginNames = plugins ?? null;
  
  const manager = getPluginManager();
  manager.autoDiscoverPlugins();
  
  if (plugins) {
    for (const name of plugins) {
      manager.enable(name);
    }
  } else {
    for (const info of manager.listPlugins()) {
      manager.enable(info.name);
    }
  }
}

/**
 * Disable plugins.
 * Python parity: praisonaiagents/plugins/__init__.py
 */
export function disable(plugins?: string[]): void {
  const manager = getPluginManager();
  
  if (plugins) {
    for (const name of plugins) {
      manager.disable(name);
    }
  } else {
    _pluginsEnabled = false;
    _enabledPluginNames = null;
    for (const info of manager.listPlugins()) {
      manager.disable(info.name);
    }
  }
}

/**
 * List all plugins.
 * Python parity: praisonaiagents/plugins/__init__.py
 */
export function listPlugins(): PluginInfo[] {
  return getPluginManager().listPlugins();
}

/**
 * Check if plugins are enabled.
 * Python parity: praisonaiagents/plugins/__init__.py
 */
export function isEnabled(name?: string): boolean {
  if (name === undefined) {
    return _pluginsEnabled;
  }
  return getPluginManager().isEnabled(name);
}
