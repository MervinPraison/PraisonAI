import { Agent } from '../../../src/agent';
import { Task } from '../../../src/agent/types';

describe('Agent Integration', () => {
  let agent: Agent;

  beforeEach(() => {
    agent = new Agent({
      name: 'IntegrationTestAgent',
      instructions: 'Test agent with tools',
      verbose: true
    });
  });

  describe('Task Execution', () => {
    it('should execute simple task', async () => {
      const result = await agent.execute('Simple test task');
      expect(result).toBeTruthy();
    });

    it('should execute complex task', async () => {
      const task = new Task({
        name: 'complex-task',
        description: 'A complex test task',
        expected_output: 'Task completed successfully',
        dependencies: [
          new Task({
            name: 'step-1',
            description: 'First step',
            expected_output: 'Step 1 completed'
          }),
          new Task({
            name: 'step-2',
            description: 'Second step',
            expected_output: 'Step 2 completed'
          })
        ]
      });

      const taskAgent = new Agent({
        name: 'ComplexTaskAgent',
        task,
        verbose: true
      });

      const result = await taskAgent.execute('Run complex task');
      expect(result).toBeTruthy();
    });

    it('should handle task failure gracefully', async () => {
      const invalidTask = new Task({
        name: 'invalid-task',
        description: '',
        expected_output: ''
      });

      const errorAgent = new Agent({
        name: 'ErrorTaskAgent',
        task: invalidTask,
        verbose: true
      });

      await expect(errorAgent.execute('Run invalid task')).rejects.toBeTruthy();
    });
  });
});
