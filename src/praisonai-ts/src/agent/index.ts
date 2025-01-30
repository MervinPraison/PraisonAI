// Export implementation based on mode
let useTaskMode = false;

export function setTaskMode(enabled: boolean) {
  useTaskMode = enabled;
}

export { Agent, PraisonAIAgents, Task } from './proxy';
export type { AgentConfig } from './types';
export type { TaskConfig } from './types';
export type { PraisonAIAgentsConfig } from './simple';
