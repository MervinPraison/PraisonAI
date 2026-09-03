/**
 * Approval module for the PraisonAI TypeScript SDK.
 *
 * Python parity: praisonaiagents/approval (backends.py, protocols.py).
 *
 * Built-in approval backends (auto-approve, console, agent, callback), the
 * Python-shaped request/decision types and the bridge into the existing
 * `ApprovalManager` from `src/ai/tool-approval.ts`.
 */

export * from './backends';
