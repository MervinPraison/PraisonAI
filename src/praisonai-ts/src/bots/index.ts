/**
 * Bots module for the PraisonAI TypeScript SDK.
 *
 * Python parity: praisonaiagents/bots (protocols.py, base.py, config.py).
 *
 * Contracts, capability descriptors and the inheritable
 * {@link BasePlatformAdapter} for messaging-platform adapters. Concrete
 * platform adapters (Telegram, Discord, Slack, ...) live outside the core SDK.
 */

export * from './protocols';
// (RunStatus is re-exported from the package root as BotRunStatus.)
export * from './base';
export * from './config';
