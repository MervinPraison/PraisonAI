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

  async start(prompt: string, previousResult?: string): Promise<string> {
    if (this.simpleAgent) {
      return this.simpleAgent.start(prompt, previousResult);
    } else if (this.taskAgent) {
      // For task agents, we'll use execute but wrap the prompt in a simple task
      const task = new Task({
        name: 'Start Task',
        description: prompt,
        expected_output: 'A response to the prompt',
        dependencies: []
      });
      return this.taskAgent.execute(task, [previousResult]);
    }
    throw new Error('No agent implementation available');
  }

  async chat(prompt: string, previousResult?: string): Promise<string> {
    if (this.simpleAgent) {
      return this.simpleAgent.chat(prompt, previousResult);
    } else if (this.taskAgent) {
      // For task agents, we'll use execute but wrap the prompt in a simple task
      const task = new Task({
        name: 'Chat Task',
        description: prompt,
        expected_output: 'A response to the chat prompt',
        dependencies: []
      });
      return this.taskAgent.execute(task, [previousResult]);
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
      // If tasks are strings, use simple mode
      if (typeof config.tasks[0] === 'string') {
        this.simpleImpl = new SimplePraisonAIAgents({
          agents: config.agents,
          tasks: config.tasks,
          verbose: config.verbose,
          process: config.process
        });
      } else {
        // Otherwise, use task mode
        this.taskImpl = new TaskPraisonAIAgents({
          agents: config.agents,
          tasks: config.tasks,
          verbose: config.verbose,
          process: config.process,
          manager_llm: config.manager_llm
        });
      }
    } else {
      throw new Error('No tasks provided');
    }
  }

  async start(): Promise<string[]> {
    if (this.simpleImpl) {
      return this.simpleImpl.start();
    } else if (this.taskImpl) {
      return this.taskImpl.start();
    }
    throw new Error('No implementation available');
  }

  async chat(): Promise<string[]> {
    if (this.simpleImpl) {
      return this.simpleImpl.chat();
    } else if (this.taskImpl) {
      // For task-based implementation, start() is equivalent to chat()
      return this.taskImpl.start();
    }
    throw new Error('No implementation available');
  }
}

export { Task } from './types';
