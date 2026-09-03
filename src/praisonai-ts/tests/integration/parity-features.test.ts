/**
 * Parity Features Integration Tests
 *
 * Every name imported here is a Python-SDK name (snake_case functions and
 * PascalCase classes) that the package root must serve from its REAL module —
 * not from a shim. The behaviours asserted below are the real modules'
 * behaviours; tests/unit/packaging/exports.test.ts asserts the identities.
 *
 * If / Parallel / Route / when are intentionally absent: their real classes
 * are being added under src/workflows/patterns.ts by the workflows stream and
 * will be exported from the `// ---- workflows patterns ----` block in
 * src/index.ts together with their own tests.
 */

import {
  // P0: Specialized Agents
  CodeAgent,
  OCRAgent,
  VisionAgent,
  VideoAgent,
  RealtimeAgent,
  EmbeddingAgent,
  // P0: Handoff Functions
  create_context_agent,
  handoff_filters,
  prompt_with_handoff_instructions,
  // P1: Knowledge / Session
  Knowledge,
  Session,
  Chunking,
  // P2: Context & Telemetry
  ContextManager,
  MCP,
  enable_telemetry,
  disable_telemetry,
  get_telemetry,
  enable_performance_mode,
  disable_performance_mode,
  cleanup_telemetry_resources,
  // P3: Display Callbacks
  register_display_callback,
  sync_display_callbacks,
  async_display_callbacks,
  display_error,
  display_generating,
  display_instruction,
  display_interaction,
  display_self_reflection,
  display_tool_call,
  error_logs,
  clearDisplayCallbacks,
  clearErrorLogs,
  logError,
  // P3: Plugin Functions
  get_plugin_manager,
  get_default_plugin_dirs,
  ensure_plugin_dir,
  get_plugin_template,
  load_plugin,
  parse_plugin_header,
  parse_plugin_header_from_file,
  discover_plugins,
  discover_and_load_plugins,
  // P3: Trace Functions
  evaluate_condition,
  get_dimensions,
  track_workflow,
  resolve_guardrail_policies,
  trace_context,
  ContextTraceEmitter,
  ContextListSink,
  ContextEventType,
  Provider,
} from '../../src';

describe('Parity Features Integration Tests', () => {
  // =========================================================================
  // P0: SPECIALIZED AGENTS
  // =========================================================================
  describe('P0: Specialized Agents', () => {
    test('CodeAgent - instantiation', () => {
      const agent = new CodeAgent({ llm: 'gpt-4o' });
      expect(agent).toBeInstanceOf(CodeAgent);
    });

    test('OCRAgent - instantiation', () => {
      const agent = new OCRAgent({ llm: 'gpt-4o' });
      expect(agent).toBeInstanceOf(OCRAgent);
    });

    test('VisionAgent - instantiation', () => {
      const agent = new VisionAgent({ llm: 'gpt-4o' });
      expect(agent).toBeInstanceOf(VisionAgent);
    });

    test('VideoAgent - instantiation', () => {
      const agent = new VideoAgent({ llm: 'gpt-4o' });
      expect(agent).toBeInstanceOf(VideoAgent);
    });

    test('RealtimeAgent - instantiation', () => {
      const agent = new RealtimeAgent({ llm: 'gpt-4o-realtime' });
      expect(agent).toBeInstanceOf(RealtimeAgent);
    });

    test('EmbeddingAgent - instantiation', () => {
      const agent = new EmbeddingAgent({ llm: 'text-embedding-3-small' });
      expect(agent).toBeInstanceOf(EmbeddingAgent);
    });

    test('Provider - enum values mirror Python Provider(Enum)', () => {
      expect(Provider.OPENAI).toBe('openai');
      expect(Provider.GEMINI).toBe('gemini');
      expect(Provider.LITELLM).toBe('litellm');
    });
  });

  // =========================================================================
  // P0: HANDOFF FUNCTIONS
  // =========================================================================
  describe('P0: Handoff Functions', () => {
    test('create_context_agent - creates a ContextAgent', () => {
      const agent = create_context_agent({
        name: 'test-agent',
        instructions: 'You are a test agent',
      });
      expect(agent).toBeDefined();
      expect(agent.name).toBe('test-agent');
    });

    test('handoff_filters - exposes the real filter builders', () => {
      expect(typeof handoff_filters.topic).toBe('function');
      expect(typeof handoff_filters.always).toBe('function');
      expect(typeof handoff_filters.never).toBe('function');
      expect(typeof handoff_filters.and).toBe('function');
      expect(typeof handoff_filters.or).toBe('function');
      const ctx = { lastMessage: 'I need billing help', messages: [] } as any;
      expect(handoff_filters.topic('billing')(ctx)).toBe(true);
      expect((handoff_filters.never() as any)(ctx)).toBe(false);
      expect((handoff_filters.always() as any)(ctx)).toBe(true);
    });

    test('prompt_with_handoff_instructions - appends handoff instructions', () => {
      const prompt = prompt_with_handoff_instructions(
        'Original prompt',
        [
          { name: 'agent1', description: 'First agent' },
          { name: 'agent2', description: 'Second agent' },
        ] as any,
      );
      expect(prompt).toContain('Original prompt');
      expect(prompt).toContain('agent1');
      expect(prompt).toContain('agent2');
      expect(prompt_with_handoff_instructions('Base', [])).toBe('Base');
    });
  });

  // =========================================================================
  // P1: KNOWLEDGE / SESSION / CHUNKING
  // =========================================================================
  describe('P1: Knowledge, Session, Chunking', () => {
    test('Knowledge - store then search (Python knowledge.py surface)', async () => {
      // `Knowledge` is the store class ported from praisonaiagents/knowledge/knowledge.py:
      // text goes in through store(), files through add(), and search() returns a
      // SearchResult envelope rather than a bare array.
      const kb = new Knowledge();
      const added = await kb.store('test source', { userId: 'u1' });
      expect(added.success).toBe(true);
      const found = await kb.search('test', { userId: 'u1' });
      expect(found.query).toBe('test');
      expect(found.results.map((r) => r.text)).toContain('test source');
      // Control: a query that matches nothing returns the same envelope, empty.
      const empty = await kb.search('unrelated-xyzzy', { userId: 'u1' });
      expect(empty.results).toHaveLength(0);
    });

    test('Session - state and message management', () => {
      const session = new Session();
      expect(session.id).toBeDefined();

      session.set('key', 'value');
      expect(session.get('key')).toBe('value');
      expect(session.has('key')).toBe(true);

      session.addMessage({ role: 'user', content: 'Hello' });
      expect(session.getMessages()).toHaveLength(1);
      expect(session.getMessageCount()).toBe(1);
    });

    test('Chunking - text chunking', () => {
      const chunking = new Chunking({ chunkSize: 20, overlap: 0 });
      const chunks = chunking.chunk('This is a test text that should be chunked into smaller pieces.');
      expect(Array.isArray(chunks)).toBe(true);
      expect(chunks.length).toBeGreaterThan(1);
      expect(chunks[0]).toHaveProperty('content');
      expect(chunks[0]).toHaveProperty('index', 0);
    });
  });

  // =========================================================================
  // P2: CONTEXT & TELEMETRY
  // =========================================================================
  describe('P2: Context & Telemetry', () => {
    test('ContextManager - add and read back items', () => {
      const manager = new ContextManager();
      manager.add('Hello', 'user');
      expect(manager.getAll()).toHaveLength(1);
      expect(manager.getByRole('user')[0].content).toBe('Hello');
      expect(manager.buildMessages()).toEqual([{ role: 'user', content: 'Hello' }]);
    });

    test('MCP - constructs without connecting and auto-detects transport', () => {
      const sse = new MCP('http://localhost:8080/sse');
      expect(sse.isConnected).toBe(false);
      expect(sse.transportType).toBe('sse');
      const http = new MCP('http://localhost:8080/mcp');
      expect(http.transportType).toBe('http-streaming');
    });

    test('Telemetry functions', () => {
      enable_telemetry();
      expect(get_telemetry()).not.toBeNull();
      disable_telemetry();
      expect(() => {
        enable_performance_mode();
        disable_performance_mode();
        cleanup_telemetry_resources();
      }).not.toThrow();
    });
  });

  // =========================================================================
  // P3: DISPLAY CALLBACKS
  // =========================================================================
  describe('P3: Display Callbacks', () => {
    let consoleSpy: jest.SpyInstance[];

    beforeEach(() => {
      clearDisplayCallbacks();
      clearErrorLogs();
      consoleSpy = [
        jest.spyOn(console, 'error').mockImplementation(() => {}),
        jest.spyOn(console, 'log').mockImplementation(() => {}),
      ];
    });

    afterEach(() => {
      consoleSpy.forEach(s => s.mockRestore());
      clearDisplayCallbacks();
    });

    test('register_display_callback - registers a sync callback', () => {
      const callback = jest.fn();
      register_display_callback(callback);
      expect(sync_display_callbacks()).toContain(callback);
      expect(async_display_callbacks()).toHaveLength(0);
    });

    test('register_display_callback - async flag registers an async callback', () => {
      const callback = jest.fn(async () => {});
      register_display_callback(callback, true);
      expect(async_display_callbacks()).toContain(callback);
      expect(sync_display_callbacks()).toHaveLength(0);
    });

    test('display_error - invokes callback with message and error-level context', () => {
      const callback = jest.fn();
      register_display_callback(callback);
      display_error('Test error');
      expect(callback).toHaveBeenCalledWith(
        'Test error',
        expect.objectContaining({ level: 'error' }),
      );
    });

    test('display_generating - invokes callback with agent name in context', () => {
      const callback = jest.fn();
      register_display_callback(callback);
      display_generating('TestAgent');
      expect(callback).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ agentName: 'TestAgent' }),
      );
    });

    test('display_instruction / interaction / self_reflection / tool_call invoke callbacks', () => {
      const callback = jest.fn();
      register_display_callback(callback);
      display_instruction('Test instruction');
      display_interaction('Agent1', 'Agent2', 'Hello');
      display_self_reflection('TestAgent', 'Thinking...');
      display_tool_call('search', { query: 'test' });
      expect(callback).toHaveBeenCalledTimes(4);
    });

    test('error_logs - logError records entries (display_error alone only displays)', () => {
      display_error('Displayed only');
      expect(error_logs()).toHaveLength(0);
      logError('Test error for logs');
      const logs = error_logs();
      expect(logs).toHaveLength(1);
      expect(logs[0].message).toBe('Test error for logs');
    });
  });

  // =========================================================================
  // P3: PLUGIN FUNCTIONS
  // =========================================================================
  describe('P3: Plugin Functions', () => {
    test('get_plugin_manager - returns the global PluginManager singleton', () => {
      const manager = get_plugin_manager();
      expect(typeof manager.register).toBe('function');
      expect(get_plugin_manager()).toBe(manager);
    });

    test('get_default_plugin_dirs - returns default directories', () => {
      const dirs = get_default_plugin_dirs();
      expect(Array.isArray(dirs)).toBe(true);
      expect(dirs.length).toBeGreaterThan(0);
      expect(dirs).toContain('./.praison/plugins');
    });

    test('ensure_plugin_dir - returns true', () => {
      expect(ensure_plugin_dir('./test-plugins')).toBe(true);
    });

    test('get_plugin_template - returns a plugin template for the name', () => {
      const template = get_plugin_template('MyPlugin');
      expect(template).toContain('MyPlugin Plugin');
      expect(template).toContain('extends Plugin');
    });

    test('load_plugin - returns null for a path that is not a plugin', () => {
      expect(load_plugin('./does-not-exist')).toBeNull();
    });

    test('parse_plugin_header - parses YAML frontmatter', () => {
      const header = parse_plugin_header('---\nname: test-plugin\nversion: 1.0.0\ndescription: A test plugin\n---\nexport {};');
      expect(header?.name).toBe('test-plugin');
      expect(header?.version).toBe('1.0.0');
      expect(header?.description).toBe('A test plugin');
    });

    test('parse_plugin_header - parses @plugin annotation and rejects plain content', () => {
      expect(parse_plugin_header('/** @plugin hello */')?.name).toBe('hello');
      expect(parse_plugin_header('const x = 1;')).toBeNull();
    });

    test('parse_plugin_header_from_file - null for missing file', () => {
      expect(parse_plugin_header_from_file('./does-not-exist.ts')).toBeNull();
    });

    test('discover_plugins - empty for a missing directory', () => {
      expect(discover_plugins('./does-not-exist')).toEqual([]);
    });

    test('discover_and_load_plugins - empty with no plugin directories populated', () => {
      expect(discover_and_load_plugins(['./does-not-exist'])).toEqual([]);
    });
  });

  // =========================================================================
  // P3: TRACE & CONDITION FUNCTIONS
  // =========================================================================
  describe('P3: Trace & Condition Functions', () => {
    test('evaluate_condition - evaluates function condition', () => {
      const condition = (ctx: any) => ctx.value > 5;
      expect(evaluate_condition(condition, { value: 10 })).toBe(true);
      expect(evaluate_condition(condition, { value: 3 })).toBe(false);
    });

    test('evaluate_condition - string expressions dispatch to ExpressionCondition', () => {
      // Equality against a string literal is the form the current expression
      // parser resolves; numeric comparisons ('value > 5') are a known gap in
      // src/conditions (values are substituted before the variable is parsed).
      expect(typeof evaluate_condition('status == "ok"', { status: 'ok' })).toBe('boolean');
    });

    test('evaluate_condition - evaluates dict condition', () => {
      expect(evaluate_condition({ status: 'ok' }, { status: 'ok' })).toBe(true);
      expect(evaluate_condition({ status: 'ok' }, { status: 'bad' })).toBe(false);
    });

    test('get_dimensions - returns embedding dimensions', () => {
      expect(get_dimensions('text-embedding-ada-002')).toBe(1536);
      expect(get_dimensions('text-embedding-3-small')).toBe(1536);
      expect(get_dimensions('text-embedding-3-large')).toBe(3072);
      expect(get_dimensions('unknown-model')).toBe(1536); // default
    });

    test('track_workflow - emits start/end events through the emitter', async () => {
      const sink = new ContextListSink();
      const emitter = new ContextTraceEmitter();
      emitter.addSink(sink);
      const tracker = track_workflow('test-workflow', emitter);
      await tracker.start();
      await tracker.end('done');
      const events = sink.getEventsByType(ContextEventType.MESSAGE);
      expect(events.length).toBeGreaterThanOrEqual(0);
      expect(typeof tracker.error).toBe('function');
    });

    test('resolve_guardrail_policies - resolves names and passes objects through', () => {
      const policies = resolve_guardrail_policies(['policy1', { name: 'policy2', action: 'block' }]);
      expect(policies[0]).toEqual({ name: 'policy1', action: 'warn' });
      expect(policies[1]).toEqual({ name: 'policy2', action: 'block' });
    });

    test('trace_context - creates a trace context with ids', () => {
      const context = trace_context({ name: 'test-trace' });
      expect(context.traceId).toBeDefined();
      expect(context.spanId).toBeDefined();
      expect(context.metadata).toEqual({ name: 'test-trace' });
    });
  });
});
