/**
 * A2UI integration facade.
 *
 * Python parity: praisonaiagents/ui/a2ui/__init__.py (and the adapter
 * signatures in praisonaiagents/ui/a2ui/adapter.py; `A2UI_MIME_TYPE` and
 * `A2UIToolResultProtocol` from praisonaiagents/ui/protocols.py).
 *
 * Python's `A2UI` is a 15-line facade whose static methods lazily import the
 * optional `a2ui-agent-sdk`. TypeScript has no equivalent package to import,
 * so the facade delegates to an injectable {@link A2UIAdapter}: install one
 * with {@link A2UI.useAdapter} (for example a thin wrapper around an A2UI
 * JavaScript SDK, or a stub in tests). Without an adapter every method throws
 * an {@link A2UINotInstalledError} with a clear "no A2UI adapter installed"
 * message, mirroring Python's ImportError when the SDK is missing.
 *
 * @example
 * ```typescript
 * import { A2UI } from 'praisonai';
 *
 * A2UI.useAdapter(myAdapter);
 * const part = A2UI.createPart({ createSurface: { ... } });
 * const prompt = A2UI.systemPrompt('You are a helpful assistant.');
 * ```
 */

/** MIME type of an A2UI part on the A2A transport. Python parity: `A2UI_MIME_TYPE`. */
export const A2UI_MIME_TYPE = 'application/json+a2ui';

/**
 * Output shape from `send_a2ui_messages`, the integrator contract for any UI.
 * Python parity: `A2UIToolResultProtocol` (TypedDict, total=False); keys are
 * the wire keys, so they stay snake_case.
 */
export interface A2UIToolResultProtocol {
  mime_type?: string;
  messages?: Array<Record<string, unknown>>;
  a2ui_part?: Record<string, unknown> | unknown[];
}

/** Keyword arguments of {@link A2UI.systemPrompt}. Python parity: `generate_a2ui_system_prompt(*, ...)`. */
export interface A2UISystemPromptOptions {
  version?: string;
  includeSchema?: boolean;
  includeExamples?: boolean;
}

/**
 * The A2UI SDK surface the facade delegates to. Method names and parameters
 * mirror praisonaiagents/ui/a2ui/adapter.py.
 */
export interface A2UIAdapter {
  /** Wrap an A2UI payload for A2A transport (MIME: application/json+a2ui). */
  createA2uiPart(a2uiData: Record<string, unknown>): unknown;
  /** True if an A2A part contains A2UI data. */
  isA2uiPart(part: unknown): boolean;
  /** Parse and split LLM text into A2A parts (text + validated A2UI JSON). */
  parseA2uiResponse(text: string): unknown[];
  /** Create a schema manager for LLM system prompts and validation. */
  getSchemaManager(version?: string, catalogs?: unknown[] | null, acceptsInlineCatalogs?: boolean): unknown;
  /** Build an LLM system prompt with embedded A2UI schema and examples. */
  generateA2uiSystemPrompt(
    roleDescription: string,
    workflowDescription?: string,
    uiDescription?: string,
    options?: A2UISystemPromptOptions,
  ): string;
}

/** Thrown by every {@link A2UI} method when no adapter is installed. */
export class A2UINotInstalledError extends Error {
  constructor(method: string) {
    super(
      `A2UI.${method}: no A2UI adapter installed. ` +
        'Call A2UI.useAdapter(adapter) with an A2UIAdapter implementation first ' +
        '(Python: pip install praisonaiagents[a2ui]).',
    );
    this.name = 'A2UINotInstalledError';
    Object.setPrototypeOf(this, A2UINotInstalledError.prototype);
  }
}

let installedAdapter: A2UIAdapter | null = null;

function requireAdapter(method: string): A2UIAdapter {
  if (!installedAdapter) throw new A2UINotInstalledError(method);
  return installedAdapter;
}

/**
 * Optional A2UI facade.
 *
 * Python parity: `A2UI` in praisonaiagents/ui/a2ui/__init__.py. Every static
 * method delegates to the adapter installed via {@link A2UI.useAdapter}:
 *
 * - `createPart`    -> `create_a2ui_part`
 * - `isPart`        -> `is_a2ui_part`
 * - `parseResponse` -> `parse_a2ui_response`
 * - `schemaManager` -> `get_schema_manager`
 * - `systemPrompt`  -> `generate_a2ui_system_prompt`
 */
export class A2UI {
  /** Install (or, with `null`, remove) the adapter the facade delegates to. */
  static useAdapter(adapter: A2UIAdapter | null): void {
    installedAdapter = adapter;
  }

  /** Whether an adapter is currently installed. */
  static hasAdapter(): boolean {
    return installedAdapter !== null;
  }

  /** Wrap an A2UI payload for A2A transport. Python parity: `create_a2ui_part(a2ui_data)`. */
  static createPart(a2uiData: Record<string, unknown>): unknown {
    return requireAdapter('createPart').createA2uiPart(a2uiData);
  }

  /** True if an A2A part contains A2UI data. Python parity: `is_a2ui_part(part)`. */
  static isPart(part: unknown): boolean {
    return requireAdapter('isPart').isA2uiPart(part);
  }

  /** Parse LLM text into A2A parts. Python parity: `parse_a2ui_response(text)`. */
  static parseResponse(text: string): unknown[] {
    return requireAdapter('parseResponse').parseA2uiResponse(text);
  }

  /**
   * Create a schema manager. Python parity:
   * `get_schema_manager(version="0.9", catalogs=None, accepts_inline_catalogs=False)`.
   */
  static schemaManager(
    version: string = '0.9',
    catalogs: unknown[] | null = null,
    acceptsInlineCatalogs: boolean = false,
  ): unknown {
    return requireAdapter('schemaManager').getSchemaManager(version, catalogs, acceptsInlineCatalogs);
  }

  /**
   * Build an LLM system prompt with embedded A2UI schema and examples.
   * Python parity: `generate_a2ui_system_prompt(role_description,
   * workflow_description="", ui_description="", *, version="0.9",
   * include_schema=True, include_examples=True)`.
   */
  static systemPrompt(
    roleDescription: string,
    workflowDescription: string = '',
    uiDescription: string = '',
    options: A2UISystemPromptOptions = {},
  ): string {
    const { version = '0.9', includeSchema = true, includeExamples = true } = options;
    return requireAdapter('systemPrompt').generateA2uiSystemPrompt(roleDescription, workflowDescription, uiDescription, {
      version,
      includeSchema,
      includeExamples,
    });
  }
}

// Module-level twins of the Python adapter functions, delegating to the facade.

/** Python parity: `create_a2ui_part`. */
export function createA2uiPart(a2uiData: Record<string, unknown>): unknown {
  return A2UI.createPart(a2uiData);
}

/** Python parity: `is_a2ui_part`. */
export function isA2uiPart(part: unknown): boolean {
  return A2UI.isPart(part);
}

/** Python parity: `parse_a2ui_response`. */
export function parseA2uiResponse(text: string): unknown[] {
  return A2UI.parseResponse(text);
}

/** Python parity: `get_schema_manager`. */
export function getSchemaManager(
  version: string = '0.9',
  catalogs: unknown[] | null = null,
  acceptsInlineCatalogs: boolean = false,
): unknown {
  return A2UI.schemaManager(version, catalogs, acceptsInlineCatalogs);
}

/** Python parity: `generate_a2ui_system_prompt`. */
export function generateA2uiSystemPrompt(
  roleDescription: string,
  workflowDescription: string = '',
  uiDescription: string = '',
  options: A2UISystemPromptOptions = {},
): string {
  return A2UI.systemPrompt(roleDescription, workflowDescription, uiDescription, options);
}
