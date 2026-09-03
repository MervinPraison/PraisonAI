/**
 * Package-root export identity tests.
 *
 * The Python<->TS parity tracker reports a Python name as DONE only when the
 * package root serves it from a real module. These tests pin every re-wired
 * name to its real provider by object identity, so a future shim (or a stray
 * explicit re-export that shadows a star export) fails here rather than
 * silently degrading the tracker.
 */

import * as fs from 'fs';
import * as path from 'path';

// Type-only names: a missing export fails type-checking of this file.
import type {
  ContextPack,
  AudioConfig,
  CodeConfig,
  OCRConfig,
  VisionConfig,
  VideoConfig,
  RealtimeConfig,
  DeepResearchResponse,
  CodeExecutionStep,
  FileSearchCall,
  MCPCall,
  WebSearchCall,
  ContextConfig,
  ManagerConfig,
  OptimizerStrategyType,
  GuardrailResult,
} from '../../../src';

/* eslint-disable @typescript-eslint/no-var-requires */
const root = require('../../../src');

const SRC_DIR = path.resolve(__dirname, '..', '..', '..', 'src');

type Case = [rootName: string, modulePath: string, moduleName: string];

const CASES: Case[] = [
  // Session / Knowledge / Context / MCP / Chunking (previously shadowed by the shim)
  ['Session', 'session/session', 'Session'],
  ['Knowledge', 'knowledge/knowledge', 'Knowledge'],
  ['ContextManager', 'context/manager', 'ContextManager'],
  ['OptimizerStrategy', 'context/models', 'OptimizerStrategy'],
  ['MCP', 'tools/mcp', 'MCP'],
  ['Chunking', 'knowledge/chunking', 'Chunking'],
  ['createContextPack', 'rag/models', 'createContextPack'],
  // Specialized agents
  ['CodeAgent', 'agent/code', 'CodeAgent'],
  ['OCRAgent', 'agent/ocr', 'OCRAgent'],
  ['VisionAgent', 'agent/vision', 'VisionAgent'],
  ['VideoAgent', 'agent/video', 'VideoAgent'],
  ['RealtimeAgent', 'agent/realtime', 'RealtimeAgent'],
  ['EmbeddingAgent', 'agent/embedding', 'EmbeddingAgent'],
  ['Provider', 'agent/research', 'Provider'],
  // Handoff / context agent
  ['create_context_agent', 'agent/context', 'createContextAgent'],
  ['handoff_filters', 'agent/handoff', 'handoffFilters'],
  ['prompt_with_handoff_instructions', 'agent/handoff', 'promptWithHandoffInstructions'],
  // Telemetry
  ['enable_telemetry', 'telemetry', 'enableTelemetry'],
  ['disable_telemetry', 'telemetry', 'disableTelemetry'],
  ['get_telemetry', 'telemetry', 'getTelemetry'],
  ['enable_performance_mode', 'telemetry', 'enablePerformanceMode'],
  ['disable_performance_mode', 'telemetry', 'disablePerformanceMode'],
  ['cleanup_telemetry_resources', 'telemetry', 'cleanupTelemetryResources'],
  // Display
  ['register_display_callback', 'display', 'registerDisplayCallback'],
  ['sync_display_callbacks', 'display', 'syncDisplayCallbacks'],
  ['async_display_callbacks', 'display', 'asyncDisplayCallbacks'],
  ['display_error', 'display', 'displayError'],
  ['display_generating', 'display', 'displayGenerating'],
  ['display_instruction', 'display', 'displayInstruction'],
  ['display_interaction', 'display', 'displayInteraction'],
  ['display_self_reflection', 'display', 'displaySelfReflection'],
  ['display_tool_call', 'display', 'displayToolCall'],
  ['error_logs', 'display', 'errorLogs'],
  // Plugins
  ['get_plugin_manager', 'plugins', 'getPluginManager'],
  ['get_default_plugin_dirs', 'plugins', 'getDefaultPluginDirs'],
  ['ensure_plugin_dir', 'plugins', 'ensurePluginDir'],
  ['get_plugin_template', 'plugins', 'getPluginTemplate'],
  ['load_plugin', 'plugins', 'loadPlugin'],
  ['parse_plugin_header', 'plugins', 'parsePluginHeader'],
  ['parse_plugin_header_from_file', 'plugins', 'parsePluginHeaderFromFile'],
  ['discover_plugins', 'plugins', 'discoverPlugins'],
  ['discover_and_load_plugins', 'plugins', 'discoverAndLoadPlugins'],
  // Trace / conditions / embeddings / protocols
  ['evaluate_condition', 'conditions', 'evaluateCondition'],
  ['get_dimensions', 'embeddings', 'getDimensions'],
  ['track_workflow', 'trace', 'trackWorkflow'],
  ['trace_context', 'trace', 'traceContext'],
  ['resolve_guardrail_policies', 'protocols', 'resolveGuardrailPolicies'],
];

describe('package root serves Python-parity names from their real modules', () => {
  test.each(CASES)('%s === %s.%s', (rootName, modulePath, moduleName) => {
    const mod = require(path.join(SRC_DIR, modulePath));
    expect(mod[moduleName]).toBeDefined();
    expect(root[rootName]).toBe(mod[moduleName]);
  });

  test('MCP at the root is the transport-aware client, not the SSE-only one', () => {
    const sseOnly = require(path.join(SRC_DIR, 'tools/mcpSse')).MCP;
    expect(root.MCP).not.toBe(sseOnly);
    expect(new root.MCP('http://localhost/mcp').transportType).toBe('http-streaming');
  });

  test('Provider mirrors the Python enum members', () => {
    expect(root.Provider).toEqual({ OPENAI: 'openai', GEMINI: 'gemini', LITELLM: 'litellm' });
  });

  test('type-only parity names are exported (compile-time check)', () => {
    // Usage keeps the type imports live; the real assertion is that this file compiles.
    const pack: Partial<ContextPack> = {};
    const audio: AudioConfig = { voice: 'alloy', responseFormat: 'mp3' };
    const cfgs: [
      Partial<CodeConfig>, Partial<OCRConfig>, Partial<VisionConfig>, Partial<VideoConfig>,
      Partial<RealtimeConfig>, Partial<DeepResearchResponse>, Partial<CodeExecutionStep>,
      Partial<FileSearchCall>, Partial<MCPCall>, Partial<WebSearchCall>, Partial<ContextConfig>,
      Partial<ManagerConfig>, Partial<GuardrailResult>,
    ] = [{}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}];
    const strategy: OptimizerStrategyType = 'balanced' as OptimizerStrategyType;
    expect([pack, audio, cfgs, strategy]).toBeDefined();
  });
});

describe('the parity shim is gone', () => {
  test("src/index.ts no longer re-exports from './parity'", () => {
    const source = fs.readFileSync(path.join(SRC_DIR, 'index.ts'), 'utf8');
    expect(source).not.toContain("'./parity'");
    expect(source).not.toContain('"./parity"');
  });

  test('src/parity/ does not exist', () => {
    expect(fs.existsSync(path.join(SRC_DIR, 'parity'))).toBe(false);
  });
});
