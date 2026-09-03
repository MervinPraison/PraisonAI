/**
 * GatewayEventType parity with Python `EventType` in
 * praisonaiagents/gateway/protocols.py (exported as `GatewayEventType`).
 */

import { describe, it, expect } from '@jest/globals';
import { GatewayEventType } from '../../../src/gateway';

/** Copied verbatim from the Python enum, in declaration order. */
const PYTHON_EVENT_TYPES: Array<[string, string]> = [
  ['CONNECT', 'connect'],
  ['DISCONNECT', 'disconnect'],
  ['RECONNECT', 'reconnect'],
  ['SESSION_START', 'session_start'],
  ['SESSION_END', 'session_end'],
  ['SESSION_UPDATE', 'session_update'],
  ['AGENT_REGISTER', 'agent_register'],
  ['AGENT_UNREGISTER', 'agent_unregister'],
  ['AGENT_STATUS', 'agent_status'],
  ['MESSAGE', 'message'],
  ['MESSAGE_ACK', 'message_ack'],
  ['MESSAGE_ABORT', 'message_abort'],
  ['TYPING', 'typing'],
  ['TOKEN_STREAM', 'token_stream'],
  ['TOOL_CALL_STREAM', 'tool_call_stream'],
  ['REASONING_STREAM', 'reasoning_stream'],
  ['TOOL_PROGRESS_STREAM', 'tool_progress_stream'],
  ['STREAM_ERROR', 'stream_error'],
  ['STREAM_END', 'stream_end'],
  ['MODEL_FALLBACK_STREAM', 'model_fallback_stream'],
  ['RETRY_STREAM', 'retry_stream'],
  ['TODO_STREAM', 'todo_stream'],
  ['TOOL_RESULT_STREAM', 'tool_result_stream'],
  ['HEALTH', 'health'],
  ['ERROR', 'error'],
  ['BROADCAST', 'broadcast'],
  ['PING', 'ping'],
  ['PONG', 'pong'],
  ['CHANNEL_SUBSCRIBE', 'channel_subscribe'],
  ['CHANNEL_UNSUBSCRIBE', 'channel_unsubscribe'],
  ['CHANNEL_MESSAGE', 'channel_message'],
  ['CHANNEL_CREATED', 'channel_created'],
  ['CHANNEL_DELETED', 'channel_deleted'],
  ['PRESENCE_JOIN', 'presence_join'],
  ['PRESENCE_LEAVE', 'presence_leave'],
  ['PRESENCE_UPDATE', 'presence_update'],
  ['MESSAGE_NACK', 'message_nack'],
  ['DELIVERY_RETRY', 'delivery_retry'],
  ['POLL_REQUEST', 'poll_request'],
  ['POLL_RESPONSE', 'poll_response'],
  ['HELLO', 'hello'],
  ['HELLO_OK', 'hello_ok'],
  ['HELLO_ERROR', 'hello_error'],
];

describe('GatewayEventType', () => {
  it('has exactly the Python members with the Python string values', () => {
    const entries = Object.entries(GatewayEventType) as Array<[string, string]>;
    expect(entries).toEqual(PYTHON_EVENT_TYPES);
    expect(entries).toHaveLength(43);
  });

  it('every member is a string value (Python str, Enum) and values are unique', () => {
    const values = Object.values(GatewayEventType);
    expect(values.every((v) => typeof v === 'string')).toBe(true);
    expect(new Set(values).size).toBe(values.length);
  });

  it('control: a value not in the Python enum is absent', () => {
    expect(Object.values(GatewayEventType)).not.toContain('not_a_python_event');
  });
});
