/**
 * EscalationPipeline, EscalationTrigger and ObservabilityHooks (Python
 * parity: praisonaiagents/escalation/{pipeline,triggers,observability}.py).
 */

import {
  EscalationPipeline,
  EscalationStage,
  EscalationSignal,
  EscalationConfig,
  EscalationTrigger,
  ObservabilityHooks,
  ObservabilityEventType,
  StageContext,
} from '../../../src/escalation';

/** An agent whose chat throws on every call index in `failing` (call N == the Nth stage tried) and echoes otherwise. */
function agentFailingAt(failing: number[]) {
  const calls: string[] = [];
  let index = 0;
  return {
    calls,
    tools: [] as unknown[],
    async chat(prompt: string) {
      calls.push(prompt);
      const stage = index++;
      if (failing.includes(stage)) {
        throw new Error(`stage ${stage} failed`);
      }
      return `ok from stage ${stage}`;
    },
  };
}

describe('EscalationConfig defaults', () => {
  it('match Python', () => {
    const c = new EscalationConfig();
    expect(c.longPromptThreshold).toBe(100);
    expect(c.complexKeywordThreshold).toBe(2);
    expect(c.maxSteps).toBe(20);
    expect(c.maxTimeSeconds).toBe(300);
    expect(c.maxTokens).toBe(100000);
    expect(c.maxToolCalls).toBe(50);
    expect(c.heuristicMaxTools).toBe(3);
    expect(c.plannedMaxSteps).toBe(5);
    expect(c.autoEscalate).toBe(true);
    expect(c.autoDeescalate).toBe(true);
    expect(c.requireApprovalForWrites).toBe(true);
    expect(c.enableCheckpoints).toBe(true);
    expect(c.maxRetries).toBe(3);
    expect(c.maxIdenticalActions).toBe(3);
    expect(c.backoffFactor).toBe(1.5);
    expect(c.useRouter).toBe(true);
    expect(c.escalateModelOnFailure).toBe(true);
  });
});

describe('EscalationStage', () => {
  it('is an ordered IntEnum DIRECT < HEURISTIC < PLANNED < AUTONOMOUS', () => {
    expect(EscalationStage.DIRECT).toBe(0);
    expect(EscalationStage.HEURISTIC).toBe(1);
    expect(EscalationStage.PLANNED).toBe(2);
    expect(EscalationStage.AUTONOMOUS).toBe(3);
  });
});

describe('EscalationTrigger', () => {
  it('keeps simple questions at DIRECT', () => {
    const trigger = new EscalationTrigger();
    const signals = trigger.analyze('What is a monad?');
    expect(signals.has(EscalationSignal.SIMPLE_QUESTION)).toBe(true);
    expect(trigger.recommendStage(signals)).toBe(EscalationStage.DIRECT);
  });

  it('recommends HEURISTIC for file references and PLANNED for edit intent', () => {
    const trigger = new EscalationTrigger();
    expect(trigger.recommendStage(trigger.analyze('Look at src/app.ts'))).toBe(EscalationStage.HEURISTIC);
    expect(trigger.recommendStage(trigger.analyze('Please fix the login bug'))).toBe(EscalationStage.PLANNED);
  });

  it('recommends AUTONOMOUS for refactor intent', () => {
    const trigger = new EscalationTrigger();
    const signals = trigger.analyze('Refactor the auth module');
    expect(signals.has(EscalationSignal.REFACTOR_INTENT)).toBe(true);
    expect(trigger.recommendStage(signals)).toBe(EscalationStage.AUTONOMOUS);
  });

  it('escalates one stage on failure signals from the current stage', () => {
    const trigger = new EscalationTrigger();
    const signals = new Set([EscalationSignal.TOOL_FAILURE]);
    expect(trigger.recommendStage(signals, EscalationStage.HEURISTIC)).toBe(EscalationStage.PLANNED);
    expect(trigger.shouldEscalate(signals, EscalationStage.HEURISTIC)).toBe(true);
    expect(trigger.recommendStage(signals, EscalationStage.AUTONOMOUS)).toBe(EscalationStage.AUTONOMOUS);
  });
});

describe('EscalationPipeline', () => {
  it('escalates stage by stage on failure and stops at the first success', async () => {
    const agent = agentFailingAt([EscalationStage.DIRECT, EscalationStage.HEURISTIC]);
    const transitions: Array<[EscalationStage, EscalationStage]> = [];
    const pipeline = new EscalationPipeline({
      agent,
      config: { autoDeescalate: false },
      onStageChange: (from, to) => transitions.push([from, to]),
      doomLoopConfig: { initialBackoff: 0 },
    });

    const result = await pipeline.executeAtStage('do the thing', EscalationStage.DIRECT);

    expect(result.success).toBe(true);
    expect(result.response).toBe('ok from stage 2');
    expect(result.initialStage).toBe(EscalationStage.DIRECT);
    expect(result.finalStage).toBe(EscalationStage.PLANNED);
    expect(result.escalations).toBe(2);
    expect(result.wasEscalated).toBe(true);
    expect(transitions).toEqual([
      [EscalationStage.DIRECT, EscalationStage.HEURISTIC],
      [EscalationStage.HEURISTIC, EscalationStage.PLANNED],
    ]);
    // Exactly three chats: no call for AUTONOMOUS once PLANNED succeeded.
    expect(agent.calls).toHaveLength(3);
    expect(agent.calls[2]).toContain('Create a brief plan (max 5 steps)');
    expect(result.stepsTaken).toBe(1);
  });

  it('control: a first-stage success never escalates', async () => {
    const agent = agentFailingAt([]);
    const pipeline = new EscalationPipeline({ agent, config: { autoDeescalate: false } });
    const result = await pipeline.executeAtStage('hi', EscalationStage.DIRECT);
    expect(result.escalations).toBe(0);
    expect(result.finalStage).toBe(EscalationStage.DIRECT);
    expect(agent.calls).toEqual(['hi']);
  });

  it('strips tools during the DIRECT stage and restores them afterwards', async () => {
    const original = [{ name: 'run_shell' }];
    let toolsSeenByChat: unknown;
    const agent = {
      calls: [] as string[],
      tools: original,
      async chat(prompt: string) {
        this.calls.push(prompt);
        toolsSeenByChat = this.tools;
        return 'ok';
      },
    };
    const pipeline = new EscalationPipeline({ agent, config: { autoDeescalate: false } });
    await pipeline.executeAtStage('hi', EscalationStage.DIRECT);
    expect(toolsSeenByChat).toEqual([]);
    // Restored after the call.
    expect(agent.tools).toBe(original);
  });

  it('stops at AUTONOMOUS when every stage fails and reports the failure', async () => {
    const agent = agentFailingAt([0, 1, 2, 3]);
    const pipeline = new EscalationPipeline({ agent, doomLoopConfig: { initialBackoff: 0 } });
    const result = await pipeline.executeAtStage('x', EscalationStage.DIRECT);
    expect(result.finalStage).toBe(EscalationStage.AUTONOMOUS);
    expect(result.escalations).toBe(3);
    expect(result.response).toBe('stage 3 failed');
    expect(agent.calls).toHaveLength(4);
  });

  it('with autoEscalate off, retries the stage until the doom-loop detector gives up (Python parity)', async () => {
    const agent = agentFailingAt([0, 1, 2, 3, 4, 5, 6, 7]);
    const pipeline = new EscalationPipeline({
      agent,
      config: { autoEscalate: false },
      doomLoopConfig: { initialBackoff: 0 },
    });
    const result = await pipeline.executeAtStage('x', EscalationStage.DIRECT);
    expect(result.finalStage).toBe(EscalationStage.DIRECT);
    expect(result.escalations).toBe(0);
    expect(result.success).toBe(false);
    // 3 identical stage_DIRECT actions trip REPEATED_ACTION (recovery attempt 1),
    // the 4th trips it again and exhausts maxRecoveryAttempts (2).
    expect(agent.calls).toHaveLength(4);
    expect(result.warnings).toContain('Escalating model due to loop detection');
    expect(result.errors).toEqual(['Max recovery attempts reached']);
  });

  it('reports "Agent not configured" without an agent', async () => {
    const pipeline = new EscalationPipeline({ config: { autoEscalate: false } });
    const result = await pipeline.executeAtStage('x', EscalationStage.DIRECT);
    expect(result.response).toBe('Agent not configured');
  });

  it('runs the injected autonomous runner at the AUTONOMOUS stage', async () => {
    const runner = jest.fn(async (prompt: string, ctx: StageContext) => `auto:${prompt}:${ctx.stage}`);
    const pipeline = new EscalationPipeline({ autonomousRunner: runner, config: { autoDeescalate: false } });
    const result = await pipeline.executeAtStage('task', EscalationStage.AUTONOMOUS);
    expect(runner).toHaveBeenCalledTimes(1);
    expect(result.response).toBe('auto:task:3');
    expect(result.success).toBe(true);
    expect(pipeline.getContext()?.steps[0].action).toBe('autonomous_response');
  });

  it('records a checkpoint before autonomous execution', async () => {
    const save = jest.fn(async () => ({ success: true, checkpoint: { id: 'cp-1' } }));
    const pipeline = new EscalationPipeline({
      agent: agentFailingAt([]),
      checkpointService: { save },
      config: { autoDeescalate: false },
    });
    const result = await pipeline.executeAtStage('task', EscalationStage.AUTONOMOUS);
    expect(save).toHaveBeenCalledWith('Before autonomous execution');
    expect(result.checkpointId).toBe('cp-1');
  });

  it('analyze() routes through the trigger', () => {
    const pipeline = new EscalationPipeline();
    expect(pipeline.analyze('What is 2+2?')).toBe(EscalationStage.DIRECT);
    expect(pipeline.analyze('Refactor the auth module')).toBe(EscalationStage.AUTONOMOUS);
  });

  it('execute() picks the initial stage from the prompt', async () => {
    const agent = agentFailingAt([]);
    const pipeline = new EscalationPipeline({ agent, config: { autoDeescalate: false } });
    const result = await pipeline.execute('Refactor the auth module', null, 'sess-1');
    expect(result.initialStage).toBe(EscalationStage.AUTONOMOUS);
    expect(result.signals).toContain(EscalationSignal.REFACTOR_INTENT);
    expect(pipeline.getContext()?.sessionId).toBe('sess-1');
    expect(agent.calls[0]).toContain('You are in autonomous mode');
  });

  it('swaps in heuristically selected tools for the HEURISTIC stage and restores them', async () => {
    const readFile = { name: 'read_file' };
    const shell = { name: 'shell' };
    const seen: unknown[][] = [];
    const agent = {
      tools: ['original'] as unknown[],
      async chat() {
        seen.push([...this.tools]);
        return 'ok';
      },
    };
    const pipeline = new EscalationPipeline({ agent, tools: [readFile, shell], config: { autoDeescalate: false } });
    await pipeline.executeAtStage('x', EscalationStage.HEURISTIC, [EscalationSignal.FILE_REFERENCES]);
    expect(seen[0]).toEqual([readFile]);
    expect(agent.tools).toEqual(['original']);
  });
});

describe('ObservabilityHooks', () => {
  it('exposes the same event types Python emits', () => {
    expect(Object.values(ObservabilityEventType).sort()).toEqual(
      [
        'stage_enter', 'stage_exit', 'stage_escalate', 'stage_deescalate',
        'execution_start', 'execution_end', 'step_start', 'step_end',
        'tool_call_start', 'tool_call_end', 'tool_call_error',
        'checkpoint_create', 'checkpoint_restore',
        'doom_loop_detected', 'recovery_attempt',
        'budget_warning', 'budget_exceeded',
      ].sort()
    );
  });

  it('delivers every emitted type to its handler and updates metrics', () => {
    const hooks = new ObservabilityHooks();
    const received: string[] = [];
    for (const type of Object.values(ObservabilityEventType)) {
      hooks.on(type, (e) => received.push(e.eventType));
    }
    hooks.setSession('s1');
    hooks.setStage(EscalationStage.PLANNED);
    for (const type of Object.values(ObservabilityEventType)) {
      hooks.emit(type, { k: 1 });
    }
    expect(received.sort()).toEqual(Object.values(ObservabilityEventType).sort());

    const metrics = hooks.getMetrics();
    expect(metrics.totalSteps).toBe(1);
    expect(metrics.toolCalls).toBe(1);
    expect(metrics.toolErrors).toBe(1);
    expect(metrics.escalations).toBe(1);
    expect(metrics.deescalations).toBe(1);
    expect(metrics.checkpointsCreated).toBe(1);
    expect(metrics.doomLoopsDetected).toBe(1);
    expect(metrics.recoveryAttempts).toBe(1);

    const first = hooks.getEvents()[0];
    expect(first.sessionId).toBe('s1');
    expect(first.stage).toBe(EscalationStage.PLANNED);
    expect(first.toDict().stage).toBe('PLANNED');
    expect(hooks.getSummary()).toMatchObject({ session_id: 's1', event_count: 17, final_stage: 'PLANNED' });
  });

  it('is silent when disabled, and off() unregisters', () => {
    const disabled = new ObservabilityHooks({ enabled: false });
    const handler = jest.fn();
    disabled.on(ObservabilityEventType.STEP_END, handler);
    disabled.emit(ObservabilityEventType.STEP_END);
    expect(handler).not.toHaveBeenCalled();
    expect(disabled.getEvents()).toHaveLength(0);

    const hooks = new ObservabilityHooks();
    hooks.on(ObservabilityEventType.STEP_END, handler);
    hooks.off(ObservabilityEventType.STEP_END, handler);
    hooks.emit(ObservabilityEventType.STEP_END);
    expect(handler).not.toHaveBeenCalled();
  });

  it('a throwing handler does not break emission', () => {
    const hooks = new ObservabilityHooks();
    const good = jest.fn();
    hooks.on(ObservabilityEventType.STAGE_ENTER, () => { throw new Error('boom'); });
    hooks.on(ObservabilityEventType.STAGE_ENTER, good);
    hooks.emit(ObservabilityEventType.STAGE_ENTER);
    expect(good).toHaveBeenCalledTimes(1);
  });

  it('receives stage and execution events from the pipeline', async () => {
    const hooks = new ObservabilityHooks();
    const types: string[] = [];
    for (const type of Object.values(ObservabilityEventType)) {
      hooks.on(type, (e) => types.push(e.eventType));
    }
    const pipeline = new EscalationPipeline({
      agent: agentFailingAt([EscalationStage.DIRECT]),
      observability: hooks,
      config: { autoDeescalate: false },
    });
    await pipeline.executeAtStage('x', EscalationStage.DIRECT, null, null, 'sess');

    expect(types).toEqual([
      'execution_start',
      'stage_enter', 'stage_exit', 'stage_escalate',
      'stage_enter', 'stage_exit',
      'execution_end',
    ]);
    expect(hooks.getMetrics().escalations).toBe(1);
    expect(hooks.getSummary()).toMatchObject({ session_id: 'sess', final_stage: 'HEURISTIC' });
  });
});
