/**
 * Unit tests for CLI Features
 */

import {
  // Slash Commands
  SlashCommandHandler,
  createSlashCommandHandler,
  parseSlashCommand,
  isSlashCommand,
  
  // Cost Tracker
  CostTracker,
  createCostTracker,
  estimateTokens,
  formatCost,
  MODEL_PRICING,
  
  // Autonomy Mode
  AutonomyManager,
  createAutonomyManager,
  MODE_POLICIES,
  
  // Scheduler
  Scheduler,
  createScheduler,
  cronExpressions,
  
  // Background Jobs
  JobQueue,
  createJobQueue,
  MemoryJobStorage,
  
  // Checkpoints
  CheckpointManager,
  createCheckpointManager,
  MemoryCheckpointStorage,
  
  // Flow Display
  FlowDisplay,
  createFlowDisplay,
  renderWorkflow,
  
  // Fast Context
  FastContext,
  createFastContext,
  getQuickContext,
  
  // Command Validator
  CommandValidator,
  DEFAULT_BLOCKED_COMMANDS
} from '../../src/cli/features';

describe('Slash Commands', () => {
  test('parseSlashCommand parses valid commands', () => {
    const result = parseSlashCommand('/help');
    expect(result).toEqual({ command: 'help', args: [] });
  });

  test('parseSlashCommand parses commands with args', () => {
    const result = parseSlashCommand('/model gpt-4');
    expect(result).toEqual({ command: 'model', args: ['gpt-4'] });
  });

  test('parseSlashCommand returns null for non-commands', () => {
    const result = parseSlashCommand('hello world');
    expect(result).toBeNull();
  });

  test('isSlashCommand detects slash commands', () => {
    expect(isSlashCommand('/help')).toBe(true);
    expect(isSlashCommand('help')).toBe(false);
    expect(isSlashCommand('  /help')).toBe(true);
  });

  test('SlashCommandHandler handles help command', async () => {
    const handler = createSlashCommandHandler();
    const result = await handler.handle('/help');
    expect(result.success).toBe(true);
    expect(result.message).toContain('Available commands');
  });

  test('SlashCommandHandler handles unknown command', async () => {
    const handler = createSlashCommandHandler();
    const result = await handler.handle('/unknown');
    expect(result.success).toBe(false);
    expect(result.message).toContain('Unknown command');
  });
});

describe('Cost Tracker', () => {
  test('createCostTracker creates instance', () => {
    const tracker = createCostTracker();
    expect(tracker).toBeInstanceOf(CostTracker);
  });

  test('addUsage tracks token usage', () => {
    const tracker = createCostTracker();
    tracker.addUsage('gpt-4o', 100, 50);
    
    const stats = tracker.getStats();
    expect(stats.totalInputTokens).toBe(100);
    expect(stats.totalOutputTokens).toBe(50);
    expect(stats.totalTokens).toBe(150);
    expect(stats.requestCount).toBe(1);
  });

  test('calculateCost uses correct pricing', () => {
    const tracker = createCostTracker();
    const cost = tracker.calculateCost('gpt-4o', 1000, 1000);
    
    // gpt-4o: input $0.005/1k, output $0.015/1k
    const expected = (1000 / 1000) * 0.005 + (1000 / 1000) * 0.015;
    expect(cost).toBeCloseTo(expected);
  });

  test('getSummary returns formatted string', () => {
    const tracker = createCostTracker();
    tracker.addUsage('gpt-4o', 100, 50);
    
    const summary = tracker.getSummary();
    expect(summary).toContain('Cost Summary');
    expect(summary).toContain('Tokens');
  });

  test('reset clears stats', () => {
    const tracker = createCostTracker();
    tracker.addUsage('gpt-4o', 100, 50);
    tracker.reset();
    
    const stats = tracker.getStats();
    expect(stats.totalTokens).toBe(0);
    expect(stats.requestCount).toBe(0);
  });

  test('estimateTokens approximates correctly', () => {
    const tokens = estimateTokens('Hello world');
    expect(tokens).toBeGreaterThan(0);
    expect(tokens).toBeLessThan(10);
  });

  test('formatCost formats small values', () => {
    expect(formatCost(0.001234)).toBe('$0.001234');
    expect(formatCost(0.05)).toBe('$0.0500');
    expect(formatCost(1.5)).toBe('$1.50');
  });

  test('MODEL_PRICING has expected models', () => {
    expect(MODEL_PRICING['gpt-4o']).toBeDefined();
    expect(MODEL_PRICING['claude-3-5-sonnet-20241022']).toBeDefined();
    expect(MODEL_PRICING['gemini-1.5-pro']).toBeDefined();
  });
});

describe('Autonomy Mode', () => {
  test('createAutonomyManager creates instance', () => {
    const manager = createAutonomyManager();
    expect(manager).toBeInstanceOf(AutonomyManager);
  });

  test('default mode is suggest', () => {
    const manager = createAutonomyManager();
    expect(manager.getMode()).toBe('suggest');
  });

  test('setMode changes mode', () => {
    const manager = createAutonomyManager();
    manager.setMode('full_auto');
    expect(manager.getMode()).toBe('full_auto');
  });

  test('requestApproval auto-approves file_read in suggest mode', async () => {
    const manager = createAutonomyManager({ mode: 'suggest' });
    const decision = await manager.requestApproval({
      type: 'file_read',
      description: 'Read config file'
    });
    expect(decision.approved).toBe(true);
  });

  test('requestApproval requires approval for file_write in suggest mode', async () => {
    const manager = createAutonomyManager({ mode: 'suggest' });
    // Without prompt callback, should deny
    const decision = await manager.requestApproval({
      type: 'file_write',
      description: 'Write to file'
    });
    expect(decision.approved).toBe(false);
  });

  test('full_auto mode auto-approves most actions', async () => {
    const manager = createAutonomyManager({ mode: 'full_auto' });
    const decision = await manager.requestApproval({
      type: 'shell_command',
      description: 'Run npm install'
    });
    expect(decision.approved).toBe(true);
  });

  test('MODE_POLICIES has all modes', () => {
    expect(MODE_POLICIES['suggest']).toBeDefined();
    expect(MODE_POLICIES['auto_edit']).toBeDefined();
    expect(MODE_POLICIES['full_auto']).toBeDefined();
  });
});

describe('Scheduler', () => {
  test('createScheduler creates instance', () => {
    const scheduler = createScheduler();
    expect(scheduler).toBeInstanceOf(Scheduler);
  });

  test('add creates task with ID', () => {
    const scheduler = createScheduler();
    const id = scheduler.add({
      name: 'test-task',
      interval: 1000,
      task: async () => 'done'
    });
    expect(id).toBeDefined();
    expect(typeof id).toBe('string');
  });

  test('getTask returns task info', () => {
    const scheduler = createScheduler();
    const id = scheduler.add({
      name: 'test-task',
      interval: 1000,
      task: async () => 'done'
    });
    
    const task = scheduler.getTask(id);
    expect(task).toBeDefined();
    expect(task?.name).toBe('test-task');
    expect(task?.status).toBe('idle');
  });

  test('remove deletes task', () => {
    const scheduler = createScheduler();
    const id = scheduler.add({
      name: 'test-task',
      interval: 1000,
      task: async () => 'done'
    });
    
    expect(scheduler.remove(id)).toBe(true);
    expect(scheduler.getTask(id)).toBeUndefined();
  });

  test('enable/disable toggles task', () => {
    const scheduler = createScheduler();
    const id = scheduler.add({
      name: 'test-task',
      interval: 1000,
      task: async () => 'done',
      enabled: true
    });
    
    scheduler.disable(id);
    expect(scheduler.getTask(id)?.enabled).toBe(false);
    
    scheduler.enable(id);
    expect(scheduler.getTask(id)?.enabled).toBe(true);
  });

  test('cronExpressions has common patterns', () => {
    expect(cronExpressions.everyMinute).toBe('* * * * *');
    expect(cronExpressions.everyHour).toBe('0 * * * *');
    expect(cronExpressions.everyDay).toBe('0 0 * * *');
  });
});

describe('Background Jobs', () => {
  test('createJobQueue creates instance', () => {
    const queue = createJobQueue();
    expect(queue).toBeInstanceOf(JobQueue);
  });

  test('add creates job', async () => {
    const queue = createJobQueue();
    const job = await queue.add('test-job', { value: 42 });
    
    expect(job.id).toBeDefined();
    expect(job.name).toBe('test-job');
    expect(job.data).toEqual({ value: 42 });
    expect(job.status).toBe('pending');
  });

  test('get retrieves job', async () => {
    const queue = createJobQueue();
    const job = await queue.add('test-job', { value: 42 });
    
    const retrieved = await queue.get(job.id);
    expect(retrieved).toBeDefined();
    expect(retrieved?.id).toBe(job.id);
  });

  test('cancel marks job as cancelled', async () => {
    const queue = createJobQueue();
    const job = await queue.add('test-job', { value: 42 });
    
    const cancelled = await queue.cancel(job.id);
    expect(cancelled).toBe(true);
    
    const retrieved = await queue.get(job.id);
    expect(retrieved?.status).toBe('cancelled');
  });

  test('MemoryJobStorage stores and retrieves', async () => {
    const storage = new MemoryJobStorage();
    const job = {
      id: 'test-1',
      name: 'test',
      data: {},
      status: 'pending' as const,
      priority: 'normal' as const,
      attempts: 0,
      maxAttempts: 3,
      createdAt: new Date()
    };
    
    await storage.save(job);
    const retrieved = await storage.get('test-1');
    expect(retrieved).toBeDefined();
    expect(retrieved?.id).toBe('test-1');
  });
});

describe('Checkpoints', () => {
  test('createCheckpointManager creates instance', () => {
    const manager = createCheckpointManager();
    expect(manager).toBeInstanceOf(CheckpointManager);
  });

  test('create saves checkpoint', async () => {
    const manager = createCheckpointManager();
    const checkpoint = await manager.create('test-checkpoint');
    
    expect(checkpoint.id).toBeDefined();
    expect(checkpoint.name).toBe('test-checkpoint');
    expect(checkpoint.timestamp).toBeInstanceOf(Date);
  });

  test('get retrieves checkpoint', async () => {
    const manager = createCheckpointManager();
    const checkpoint = await manager.create('test-checkpoint');
    
    const retrieved = await manager.get(checkpoint.id);
    expect(retrieved).toBeDefined();
    expect(retrieved?.name).toBe('test-checkpoint');
  });

  test('list returns all checkpoints', async () => {
    const manager = createCheckpointManager();
    await manager.create('checkpoint-1');
    await manager.create('checkpoint-2');
    
    const list = await manager.list();
    expect(list.length).toBe(2);
  });

  test('setState and getState work correctly', () => {
    const manager = createCheckpointManager();
    manager.setState({ key: 'value' });
    
    const state = manager.getState();
    expect(state.key).toBe('value');
  });

  test('MemoryCheckpointStorage stores and retrieves', async () => {
    const storage = new MemoryCheckpointStorage();
    const checkpoint = {
      id: 'cp-1',
      name: 'test',
      timestamp: new Date(),
      state: { key: 'value' }
    };
    
    await storage.save(checkpoint);
    const retrieved = await storage.load('cp-1');
    expect(retrieved).toBeDefined();
    expect(retrieved?.name).toBe('test');
  });
});

describe('Flow Display', () => {
  test('createFlowDisplay creates instance', () => {
    const display = createFlowDisplay();
    expect(display).toBeInstanceOf(FlowDisplay);
  });

  test('addNode adds node to graph', () => {
    const display = createFlowDisplay();
    display.addNode({ id: 'node-1', name: 'Test Node', type: 'agent' });
    
    const graph = display.getGraph();
    expect(graph.nodes.has('node-1')).toBe(true);
  });

  test('addEdge adds edge to graph', () => {
    const display = createFlowDisplay();
    display.addNode({ id: 'node-1', name: 'Node 1', type: 'start' });
    display.addNode({ id: 'node-2', name: 'Node 2', type: 'agent' });
    display.addEdge('node-1', 'node-2');
    
    const graph = display.getGraph();
    expect(graph.edges.length).toBe(1);
    expect(graph.edges[0]).toEqual({ from: 'node-1', to: 'node-2', label: undefined });
  });

  test('fromTasks builds graph', () => {
    const display = createFlowDisplay();
    display.fromTasks([
      { name: 'Step 1', type: 'agent' },
      { name: 'Step 2', type: 'tool' }
    ]);
    
    const graph = display.getGraph();
    expect(graph.nodes.size).toBe(4); // start + 2 steps + end
  });

  test('render produces text output', () => {
    const display = createFlowDisplay();
    display.fromTasks([
      { name: 'Step 1', type: 'agent' }
    ]);
    
    const output = display.render();
    expect(output).toContain('Start');
    expect(output).toContain('Step 1');
  });

  test('renderWorkflow helper works', () => {
    const output = renderWorkflow([
      { name: 'Step 1' },
      { name: 'Step 2' }
    ]);
    expect(output).toContain('Step 1');
    expect(output).toContain('Step 2');
  });
});

describe('Fast Context', () => {
  test('createFastContext creates instance', () => {
    const fc = createFastContext();
    expect(fc).toBeInstanceOf(FastContext);
  });

  test('registerSource adds sources', () => {
    const fc = createFastContext();
    fc.registerSource('test', 'custom', ['content 1', 'content 2']);
    // No error means success
  });

  test('getContext returns result', async () => {
    const fc = createFastContext({ cacheEnabled: false });
    fc.registerSource('test', 'custom', ['Hello world', 'Test content']);
    
    const result = await fc.getContext('hello');
    expect(result.context).toBeDefined();
    expect(result.sources.length).toBeGreaterThan(0);
    expect(result.tokenCount).toBeGreaterThan(0);
    expect(result.cached).toBe(false);
  });

  test('caching works', async () => {
    const fc = createFastContext({ cacheEnabled: true });
    fc.registerSource('test', 'custom', ['Hello world']);
    
    await fc.getContext('hello');
    const result2 = await fc.getContext('hello');
    
    expect(result2.cached).toBe(true);
  });

  test('clearCache clears cache', async () => {
    const fc = createFastContext({ cacheEnabled: true });
    fc.registerSource('test', 'custom', ['Hello world']);
    
    await fc.getContext('hello');
    fc.clearCache();
    
    const stats = fc.getCacheStats();
    expect(stats.size).toBe(0);
  });

  test('getQuickContext helper works', async () => {
    const context = await getQuickContext('test', ['Source 1', 'Source 2']);
    expect(context).toBeDefined();
    expect(typeof context).toBe('string');
  });
});

describe('Command Validator', () => {
  test('validates safe commands', () => {
    const validator = new CommandValidator();
    const result = validator.validate('ls -la');
    expect(result.valid).toBe(true);
  });

  test('blocks dangerous commands', () => {
    const validator = new CommandValidator();
    const result = validator.validate('rm -rf /');
    expect(result.valid).toBe(false);
    expect(result.reason).toContain('Blocked');
  });

  test('blocks shell injection', () => {
    const validator = new CommandValidator();
    const result = validator.validate('echo test; rm -rf /');
    expect(result.valid).toBe(false);
  });

  test('DEFAULT_BLOCKED_COMMANDS has dangerous patterns', () => {
    expect(DEFAULT_BLOCKED_COMMANDS).toContain('rm -rf /');
    expect(DEFAULT_BLOCKED_COMMANDS).toContain('sudo rm');
  });
});
