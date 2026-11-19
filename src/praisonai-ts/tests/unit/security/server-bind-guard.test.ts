/**
 * Every TS network server binds 127.0.0.1 by default and refuses a keyless
 * non-loopback host before listen(). Behaviour tests plus a source scan so a
 * new listen site cannot skip the shared guard (src/utils/bind-guard.ts).
 */
import fs from 'fs';
import http from 'http';
import path from 'path';
import { AgentOS } from '../../../src/os/agentos';
import { mergeConfig } from '../../../src/os/config';
import { MCPServer } from '../../../src/mcp/server';
import { N8NIntegration } from '../../../src/cli/features/n8n-integration';

const SRC = path.resolve(__dirname, '../../../src');

function post(port: number, headers: Record<string, string> = {}): Promise<number> {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: '127.0.0.1', port, method: 'POST', path: '/', headers: { 'Content-Type': 'application/json', ...headers } },
      (res) => { res.resume(); res.on('end', () => resolve(res.statusCode ?? 0)); },
    );
    req.on('error', reject);
    req.end(JSON.stringify({ event: 'x', data: {} }));
  });
}

describe('AgentOS bind guard', () => {
  afterEach(() => { delete process.env.PRAISONAI_AGENTOS_API_KEY; });

  test('serve({ host }) cannot widen a keyless loopback config', async () => {
    const app = new AgentOS({ config: { apiKey: '' } });
    const listen = jest.fn();
    jest.spyOn(app, 'getApp').mockReturnValue({ listen } as any);
    await expect(app.serve({ host: '0.0.0.0', port: 0 })).rejects.toThrow(/apiKey/);
    expect(listen).not.toHaveBeenCalled();
  });

  test.each(['10.0.0.5', '::', 'example.com'])('constructor refuses keyless %s', (host) => {
    expect(() => mergeConfig({ host })).toThrow(/apiKey/);
  });

  test('a keyed non-loopback config still constructs', () => {
    expect(() => mergeConfig({ host: '10.0.0.5', apiKey: 'k' })).not.toThrow();
  });
});

describe('MCPServer HTTP bind guard', () => {
  test('binds 127.0.0.1 by default', async () => {
    const server = new MCPServer({ logging: false });
    await server.startHttp(0);
    try {
      const addr = (server as any).httpServer.address();
      expect(addr.address).toBe('127.0.0.1');
    } finally {
      await server.stop();
    }
  });

  test('refuses a keyless non-loopback host', async () => {
    const prev = process.env.PRAISONAI_MCP_AUTH_TOKEN;
    delete process.env.PRAISONAI_MCP_AUTH_TOKEN;
    try {
      const server = new MCPServer({ logging: false });
      await expect((server.startHttp as any).call(server, 0, '0.0.0.0')).rejects.toThrow(/authToken/);
      expect((server as any).httpServer ?? null).toBeNull();
    } finally {
      if (prev !== undefined) process.env.PRAISONAI_MCP_AUTH_TOKEN = prev;
    }
  });
});

describe('N8N webhook listener bind guard', () => {
  test('refuses a keyless non-loopback host', async () => {
    const n8n = new N8NIntegration();
    await expect(
      (n8n.createWebhookListener as any)(0, async () => ({}), { host: '0.0.0.0' }),
    ).rejects.toThrow(/token/);
  });

  test('binds 127.0.0.1 by default and enforces a token when set', async () => {
    const created: http.Server[] = [];
    const orig = http.createServer;
    const spy = jest.spyOn(http, 'createServer').mockImplementation(((...a: any[]) => {
      const s = (orig as any)(...a);
      created.push(s);
      return s;
    }) as any);
    const n8n = new N8NIntegration();
    const listener = await (n8n.createWebhookListener as any)(0, async () => ({ ok: true }), { token: 'n8n-secret' });
    spy.mockRestore();
    try {
      const server = created[0]!;
      await new Promise((r) => (server.listening ? r(null) : server.once('listening', r)));
      const addr = server.address() as any;
      expect(addr.address).toBe('127.0.0.1');
      expect(await post(addr.port)).toBe(401);
      expect(await post(addr.port, { Authorization: 'Bearer wrong' })).toBe(401);
      expect(await post(addr.port, { Authorization: 'Bearer n8n-secret' })).toBe(200);
      expect(await post(addr.port, { 'X-Auth-Token': 'n8n-secret' })).toBe(200);
    } finally {
      listener.close();
    }
  });
});

// ── every listen site uses the shared guard ─────────────────────────────────

/** Files that start a server but legitimately do not call the guard. */
const EXEMPT: Record<string, string> = {};

const LISTEN_SITE = /(\.listen\s*\(|createServer\s*\(|new\s+WebSocketServer\s*\()/;

function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

function listenSites(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listenSites(full));
    else if (entry.name.endsWith('.ts') && LISTEN_SITE.test(stripComments(fs.readFileSync(full, 'utf8')))) {
      out.push(path.relative(SRC, full));
    }
  }
  return out;
}

describe('listen-site scan', () => {
  test('every server listen site calls requireBindToken', () => {
    const sites = listenSites(SRC);
    expect(sites.length).toBeGreaterThanOrEqual(3);
    const unguarded = sites.filter(
      (f) => !(f in EXEMPT) && !/requireBindToken\s*\(/.test(fs.readFileSync(path.join(SRC, f), 'utf8')),
    );
    expect(unguarded).toEqual([]);
  });

  test('control: the scan flags a listen call and ignores one in a comment', () => {
    expect(LISTEN_SITE.test(stripComments('server.listen(3000);'))).toBe(true);
    expect(LISTEN_SITE.test(stripComments('/**\n * createServer(h).listen(3000);\n */\n// app.listen(1)'))).toBe(false);
  });

  test('no server compares its token with ===', () => {
    for (const f of ['mcp/server.ts', 'os/agentos.ts']) {
      const code = fs.readFileSync(path.join(SRC, f), 'utf8');
      expect(code).not.toMatch(/===\s*this\.(authToken|config\.apiKey)/);
    }
  });
});
