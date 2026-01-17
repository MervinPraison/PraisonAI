/**
 * Hooks Module - Complete hooks and callbacks system
 * 
 * @module hooks
 */

// HooksManager - Cascade hooks for operations
export {
    HooksManager,
    createHooksManager,
    createLoggingHooks,
    createValidationHooks,
    type HookEvent,
    type HookHandler,
    type HookResult,
    type HookConfig,
    type HooksManagerConfig,
} from './manager';

// Callback Registry - Display and approval callbacks
export {
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
    type DisplayCallbackFn,
    type DisplayCallbackData,
    type ApprovalRequest,
    type ApprovalDecision,
    type ApprovalCallbackFn,
    type DisplayType,
} from './callbacks';

// Workflow Hooks - Lifecycle hooks
export {
    WorkflowHooksExecutor,
    createWorkflowHooks,
    createLoggingWorkflowHooks,
    createTimingWorkflowHooks,
    type WorkflowHooksConfig,
    type WorkflowRef,
    type StepContext,
} from './workflow-hooks';
