import { Agent as SimpleAgent, PraisonAIAgents as SimplePraisonAIAgents, SimpleAgentConfig } from './simple';
import { Agent as TaskAgent, PraisonAIAgents as TaskPraisonAIAgents, TaskAgentConfig } from './types';
import { Task } from './types';

export interface ProxyAgentConfig extends Partial<SimpleAgentConfig>, Partial<TaskAgentConfig> {
  task?: Task;
}

export class Agent {
  private simpleAgent: SimpleAgent | null = null;
  private taskAgent: TaskAgent | null = null;

  constructor(config: ProxyAgentConfig) {
    // Auto-detect mode based on task presence
    if (config.task) {
      const taskConfig: TaskAgentConfig = {
        name: config.name || 'TaskAgent',
        role: config.role || 'Assistant',
        goal: config.goal || 'Help complete the task',
        backstory: config.backstory || 'You are an AI assistant',
        verbose: config.verbose,
        llm: config.llm,
        markdown: config.markdown
      };
      this.taskAgent = new TaskAgent(taskConfig);
    } else {
      const simpleConfig: SimpleAgentConfig = {
        instructions: config.instructions || '',
        name: config.name,
        verbose: config.verbose,
        llm: config.llm,
        markdown: config.markdown
      };
      this.simpleAgent = new SimpleAgent(simpleConfig);
    }
  }

  async execute(input: Task | string): Promise<any> {
    if (this.taskAgent) {
      const task = input as Task;
      const depResults = task.dependencies.map(dep => dep.result);
      return this.taskAgent.execute(task, depResults);
    } else if (this.simpleAgent) {
      return this.simpleAgent.execute(input as string);
    }
    throw new Error('No agent implementation available');
  }
}

export class PraisonAIAgents {
  private simpleImpl: SimplePraisonAIAgents | null = null;
  private taskImpl: TaskPraisonAIAgents | null = null;

  constructor(config: any) {
    // Auto-detect mode based on tasks type
    if (Array.isArray(config.tasks) && config.tasks.length > 0) {
      const firstTask = config.tasks[0];
      if (firstTask instanceof Task) {
        this.taskImpl = new TaskPraisonAIAgents({
          agents: config.agents,
          tasks: config.tasks,
          verbose: config.verbose,
          process: config.process,
          manager_llm: config.manager_llm
        });
      } else {
        this.simpleImpl = new SimplePraisonAIAgents({
          agents: config.agents,
          tasks: config.tasks,
          verbose: config.verbose,
          process: config.process
        });
      }
    } else {
      throw new Error('No tasks provided');
    }
  }

  async start(): Promise<any[]> {
    if (this.taskImpl) {
      return this.taskImpl.start();
    } else if (this.simpleImpl) {
      return this.simpleImpl.start();
    }
    throw new Error('No implementation available');
  }
}

export { Task } from './types';
