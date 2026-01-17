/**
 * Callback Registry - Global callback system for PraisonAI TypeScript
 * 
 * Provides display and approval callbacks matching Python's callback system.
 * 
 * @example
 * ```typescript
 * import { registerDisplayCallback, registerApprovalCallback } from 'praisonai';
 * 
 * // Register display callback
 * registerDisplayCallback('agent_output', (data) => {
 *   console.log('Agent:', data.content);
 * });
 * 
 * // Register approval callback
 * registerApprovalCallback(async (action) => {
 *   return action.risk === 'low'; // Auto-approve low risk
 * });
 * ```
 */

/**
 * Display callback function type
 */
export type DisplayCallbackFn = (data: DisplayCallbackData) => void | Promise<void>;

/**
 * Display callback data
 */
export interface DisplayCallbackData {
    type: string;
    content?: string;
    agentName?: string;
    toolName?: string;
    timestamp: number;
    metadata?: Record<string, any>;
}

/**
 * Approval request
 */
export interface ApprovalRequest {
    action: string;
    arguments: Record<string, any>;
    risk: 'low' | 'medium' | 'high' | 'critical';
    toolName?: string;
    agentName?: string;
    description?: string;
}

/**
 * Approval decision
 */
export interface ApprovalDecision {
    approved: boolean;
    reason?: string;
    modifiedArgs?: Record<string, any>;
}

/**
 * Approval callback function type
 */
export type ApprovalCallbackFn = (
    request: ApprovalRequest
) => ApprovalDecision | Promise<ApprovalDecision>;

// Global callback registries
const syncDisplayCallbacks = new Map<string, DisplayCallbackFn[]>();
const asyncDisplayCallbacks = new Map<string, DisplayCallbackFn[]>();
let approvalCallback: ApprovalCallbackFn | null = null;

/**
 * Register a display callback for a specific type
 */
export function registerDisplayCallback(
    displayType: string,
    callback: DisplayCallbackFn,
    isAsync: boolean = false
): void {
    const registry = isAsync ? asyncDisplayCallbacks : syncDisplayCallbacks;

    if (!registry.has(displayType)) {
        registry.set(displayType, []);
    }

    registry.get(displayType)!.push(callback);
}

/**
 * Unregister a display callback
 */
export function unregisterDisplayCallback(
    displayType: string,
    callback: DisplayCallbackFn
): boolean {
    for (const registry of [syncDisplayCallbacks, asyncDisplayCallbacks]) {
        const callbacks = registry.get(displayType);
        if (callbacks) {
            const index = callbacks.indexOf(callback);
            if (index !== -1) {
                callbacks.splice(index, 1);
                return true;
            }
        }
    }
    return false;
}

/**
 * Register global approval callback
 */
export function registerApprovalCallback(callback: ApprovalCallbackFn): void {
    approvalCallback = callback;
}

/**
 * Clear approval callback
 */
export function clearApprovalCallback(): void {
    approvalCallback = null;
}

/**
 * Execute sync callbacks for a display type
 */
export function executeSyncCallback(
    displayType: string,
    data: Omit<DisplayCallbackData, 'type' | 'timestamp'>
): void {
    const callbacks = syncDisplayCallbacks.get(displayType);
    if (!callbacks) return;

    const fullData: DisplayCallbackData = {
        type: displayType,
        timestamp: Date.now(),
        ...data,
    };

    for (const callback of callbacks) {
        try {
            callback(fullData);
        } catch (error) {
            console.error(`[Callback] Error in ${displayType} callback:`, error);
        }
    }
}

/**
 * Execute all callbacks (sync and async) for a display type
 */
export async function executeCallback(
    displayType: string,
    data: Omit<DisplayCallbackData, 'type' | 'timestamp'>
): Promise<void> {
    const fullData: DisplayCallbackData = {
        type: displayType,
        timestamp: Date.now(),
        ...data,
    };

    // Execute sync callbacks
    const syncCallbacks = syncDisplayCallbacks.get(displayType) ?? [];
    for (const callback of syncCallbacks) {
        try {
            callback(fullData);
        } catch (error) {
            console.error(`[Callback] Error in sync ${displayType} callback:`, error);
        }
    }

    // Execute async callbacks
    const asyncCallbacks = asyncDisplayCallbacks.get(displayType) ?? [];
    await Promise.all(
        asyncCallbacks.map(async (callback) => {
            try {
                await callback(fullData);
            } catch (error) {
                console.error(`[Callback] Error in async ${displayType} callback:`, error);
            }
        })
    );
}

/**
 * Request approval for an action
 */
export async function requestApproval(
    request: ApprovalRequest
): Promise<ApprovalDecision> {
    if (!approvalCallback) {
        // No callback registered - default behavior by risk level
        if (request.risk === 'low') {
            return { approved: true };
        }
        console.warn(
            `[Approval] No callback registered. Denying ${request.risk} risk action: ${request.action}`
        );
        return { approved: false, reason: 'No approval callback registered' };
    }

    try {
        return await approvalCallback(request);
    } catch (error) {
        console.error(`[Approval] Error in approval callback:`, error);
        return { approved: false, reason: 'Approval callback error' };
    }
}

/**
 * Check if approval callback is registered
 */
export function hasApprovalCallback(): boolean {
    return approvalCallback !== null;
}

/**
 * Get registered display types
 */
export function getRegisteredDisplayTypes(): string[] {
    const types = new Set<string>();
    for (const key of syncDisplayCallbacks.keys()) types.add(key);
    for (const key of asyncDisplayCallbacks.keys()) types.add(key);
    return Array.from(types);
}

/**
 * Clear all callbacks
 */
export function clearAllCallbacks(): void {
    syncDisplayCallbacks.clear();
    asyncDisplayCallbacks.clear();
    approvalCallback = null;
}

/**
 * Common display types
 */
export const DisplayTypes = {
    AGENT_OUTPUT: 'agent_output',
    AGENT_THINKING: 'agent_thinking',
    TOOL_CALL: 'tool_call',
    TOOL_RESULT: 'tool_result',
    LLM_REQUEST: 'llm_request',
    LLM_RESPONSE: 'llm_response',
    ERROR: 'error',
    WARNING: 'warning',
    INFO: 'info',
    DEBUG: 'debug',
    WORKFLOW_START: 'workflow_start',
    WORKFLOW_COMPLETE: 'workflow_complete',
    STEP_START: 'step_start',
    STEP_COMPLETE: 'step_complete',
} as const;

export type DisplayType = typeof DisplayTypes[keyof typeof DisplayTypes];

// Default export for convenience
export default {
    registerDisplayCallback,
    unregisterDisplayCallback,
    registerApprovalCallback,
    clearApprovalCallback,
    executeSyncCallback,
    executeCallback,
    requestApproval,
    hasApprovalCallback,
    getRegisteredDisplayTypes,
    clearAllCallbacks,
    DisplayTypes,
};
