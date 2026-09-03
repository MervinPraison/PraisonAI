/**
 * Managed Agent backends: provider-agnostic events and the backend contract.
 *
 * Python parity: praisonaiagents/managed/ (events) and
 * praisonaiagents/agent/protocols.py (`ManagedBackendProtocol`).
 */

export {
  ManagedEventType,
  ManagedStopReason,
  ManagedEvent,
  AgentMessageEvent,
  ToolUseEvent,
  CustomToolUseEvent,
  ToolConfirmationEvent,
  SessionIdleEvent,
  SessionRunningEvent,
  SessionErrorEvent,
  UsageEvent,
} from './events';
export type {
  ManagedEventInit,
  ManagedContentBlock,
  AgentMessageEventInit,
  ToolUseEventInit,
  CustomToolUseEventInit,
  ToolConfirmationEventInit,
  SessionIdleEventInit,
  SessionErrorEventInit,
  UsageEventInit,
} from './events';

export { isManagedBackend } from './protocols';
export type { ManagedBackendProtocol, ManagedBackendKwargs } from './protocols';
