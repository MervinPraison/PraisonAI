/**
 * In-Memory Database Adapter - Simple implementation for testing and development
 */

import type {
  DbAdapter,
  DbSession,
  DbMessage,
  DbRun,
  DbToolCall,
  DbTrace,
  DbSpan,
} from './types';

export class MemoryDbAdapter implements DbAdapter {
  private sessions: Map<string, DbSession> = new Map();
  private messages: Map<string, DbMessage[]> = new Map();
  private runs: Map<string, DbRun> = new Map();
  private toolCalls: Map<string, DbToolCall[]> = new Map();
  private traces: Map<string, DbTrace> = new Map();
  private spans: Map<string, DbSpan[]> = new Map();
  private connected = false;

  // Session operations
  async createSession(session: DbSession): Promise<void> {
    this.sessions.set(session.id, session);
    this.messages.set(session.id, []);
  }

  async getSession(id: string): Promise<DbSession | null> {
    return this.sessions.get(id) || null;
  }

  async updateSession(id: string, updates: Partial<DbSession>): Promise<void> {
    const session = this.sessions.get(id);
    if (session) {
      this.sessions.set(id, { ...session, ...updates, updatedAt: Date.now() });
    }
  }

  async deleteSession(id: string): Promise<void> {
    this.sessions.delete(id);
    this.messages.delete(id);
  }

  async listSessions(limit = 100, offset = 0): Promise<DbSession[]> {
    const all = Array.from(this.sessions.values());
    return all.slice(offset, offset + limit);
  }

  // Message operations
  async saveMessage(message: DbMessage): Promise<void> {
    const messages = this.messages.get(message.sessionId) || [];
    messages.push(message);
    this.messages.set(message.sessionId, messages);
  }

  async getMessages(sessionId: string, limit?: number): Promise<DbMessage[]> {
    const messages = this.messages.get(sessionId) || [];
    if (limit) {
      return messages.slice(-limit);
    }
    return messages;
  }

  async deleteMessages(sessionId: string): Promise<void> {
    this.messages.set(sessionId, []);
  }

  // Run operations
  async createRun(run: DbRun): Promise<void> {
    this.runs.set(run.id, run);
    this.toolCalls.set(run.id, []);
  }

  async getRun(id: string): Promise<DbRun | null> {
    return this.runs.get(id) || null;
  }

  async updateRun(id: string, updates: Partial<DbRun>): Promise<void> {
    const run = this.runs.get(id);
    if (run) {
      this.runs.set(id, { ...run, ...updates });
    }
  }

  async listRuns(sessionId: string, limit = 100): Promise<DbRun[]> {
    const all = Array.from(this.runs.values()).filter(r => r.sessionId === sessionId);
    return all.slice(-limit);
  }

  // Tool call operations
  async saveToolCall(toolCall: DbToolCall): Promise<void> {
    const calls = this.toolCalls.get(toolCall.runId) || [];
    calls.push(toolCall);
    this.toolCalls.set(toolCall.runId, calls);
  }

  async getToolCalls(runId: string): Promise<DbToolCall[]> {
    return this.toolCalls.get(runId) || [];
  }

  // Trace operations
  async createTrace(trace: DbTrace): Promise<void> {
    this.traces.set(trace.id, trace);
    this.spans.set(trace.id, []);
  }

  async getTrace(id: string): Promise<DbTrace | null> {
    return this.traces.get(id) || null;
  }

  async updateTrace(id: string, updates: Partial<DbTrace>): Promise<void> {
    const trace = this.traces.get(id);
    if (trace) {
      this.traces.set(id, { ...trace, ...updates });
    }
  }

  // Span operations
  async createSpan(span: DbSpan): Promise<void> {
    const spans = this.spans.get(span.traceId) || [];
    spans.push(span);
    this.spans.set(span.traceId, spans);
  }

  async getSpans(traceId: string): Promise<DbSpan[]> {
    return this.spans.get(traceId) || [];
  }

  async updateSpan(id: string, updates: Partial<DbSpan>): Promise<void> {
    for (const [traceId, spans] of this.spans) {
      const index = spans.findIndex(s => s.id === id);
      if (index !== -1) {
        spans[index] = { ...spans[index], ...updates };
        this.spans.set(traceId, spans);
        return;
      }
    }
  }

  // Lifecycle
  async connect(): Promise<void> {
    this.connected = true;
  }

  async disconnect(): Promise<void> {
    this.connected = false;
  }

  isConnected(): boolean {
    return this.connected;
  }

  // Utility methods
  clear(): void {
    this.sessions.clear();
    this.messages.clear();
    this.runs.clear();
    this.toolCalls.clear();
    this.traces.clear();
    this.spans.clear();
  }

  getStats(): { sessions: number; messages: number; runs: number } {
    let messageCount = 0;
    for (const msgs of this.messages.values()) {
      messageCount += msgs.length;
    }
    return {
      sessions: this.sessions.size,
      messages: messageCount,
      runs: this.runs.size,
    };
  }
}
