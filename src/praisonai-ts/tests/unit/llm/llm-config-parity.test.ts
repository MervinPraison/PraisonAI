/**
 * LLMConfig parity tests - every Python `LLM.__init__` parameter is accepted,
 * request-shaped ones reach the outgoing Chat Completions body, transport
 * ones reach the client, and every remaining option is honoured (see
 * llm-tool-loop.test.ts and llm-honoured-options.test.ts) so nothing is
 * reported as not yet honoured.
 */

import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import { BaseLLM, type LLMConfig } from '../../../src/llm/index';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

jest.mock('openai');

process.env.PRAISONAI_PARITY_SILENT = '1';

const FULL_CONFIG: LLMConfig = {
  model: 'gpt-4o-mini',
  temperature: 0.2,
  maxTokens: 128,
  apiKey: 'sk-test',
  baseURL: 'https://example.invalid/v1',
  timeout: 30,
  topP: 0.9,
  n: 2,
  presencePenalty: 0.5,
  frequencyPenalty: -0.5,
  logitBias: { 1234: -100 },
  responseFormat: { type: 'json_object' },
  seed: 7,
  logprobs: true,
  topLogprobs: 3,
  apiVersion: '2024-06-01',
  stopPhrases: ['END', 'STOP'],
  events: [],
  webSearch: true,
  // webFetch / claudeMemory are Anthropic-only request shapes: on an OpenAI
  // model they throw when truthy, so the acceptance config carries them as
  // `false` and llm-honoured-options.test.ts exercises them on a Claude model.
  webFetch: false,
  promptCaching: true,
  claudeMemory: false,
  failoverManager: { getNextProfile: () => null },
  auth: { apiKey: 'sk-auth' },
  maxIter: 5,
};

async function createMock(llm: BaseLLM): Promise<jest.Mock> {
  const client: any = await llm.getClient();
  return client.chat.completions.create as jest.Mock;
}

describe('LLMConfig parity', () => {
  beforeEach(() => {
    resetParityNotices();
  });

  describe('acceptance', () => {
    it('accepts every Python LLM.__init__ parameter and stores it on config', () => {
      const llm = new BaseLLM(FULL_CONFIG);
      for (const [key, value] of Object.entries(FULL_CONFIG)) {
        expect((llm.config as any)[key]).toEqual(value);
      }
    });

    it('defaults events to [] like Python', () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      expect(llm.config.events).toEqual([]);
    });

    it('leaves optional request fields undefined when not supplied (Python None)', () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      for (const key of ['timeout', 'topP', 'n', 'seed', 'logprobs', 'stopPhrases', 'maxIter', 'auth'] as const) {
        expect(llm.config[key]).toBeUndefined();
      }
    });
  });

  describe('request body wiring', () => {
    it('maps every request-shaped option to its wire name', () => {
      const llm = new BaseLLM(FULL_CONFIG);
      const body = llm.buildRequestParams([{ role: 'user', content: 'hi' }]);
      expect(body).toMatchObject({
        model: 'gpt-4o-mini',
        temperature: 0.2,
        max_tokens: 128,
        top_p: 0.9,
        n: 2,
        presence_penalty: 0.5,
        frequency_penalty: -0.5,
        logit_bias: { 1234: -100 },
        response_format: { type: 'json_object' },
        seed: 7,
        logprobs: true,
        top_logprobs: 3,
        stop: ['END', 'STOP'],
        web_search_options: { search_context_size: 'medium' },
      });
    });

    it('omits fields that were not set so provider defaults apply', () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      const body = llm.buildRequestParams([{ role: 'user', content: 'hi' }]);
      expect(Object.keys(body).sort()).toEqual(['messages', 'model']);
    });

    it('wraps a single stop phrase into an array', () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini', stopPhrases: 'END' });
      expect(llm.buildRequestParams([]).stop).toEqual(['END']);
    });

    it('passes a webSearch object through verbatim as web_search_options', () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini', webSearch: { search_context_size: 'high' } });
      expect(llm.buildRequestParams([]).web_search_options).toEqual({ search_context_size: 'high' });
    });

    it('does not send web_search_options when webSearch is false', () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini', webSearch: false });
      expect(llm.buildRequestParams([])).not.toHaveProperty('web_search_options');
    });

    it('sends the wired fields on generate()', async () => {
      const llm = new BaseLLM(FULL_CONFIG);
      const create = await createMock(llm);
      const response = await llm.generate('Hello', { systemPrompt: 'Be brief' });

      expect(response.text).toBe('Mock response');
      expect(create).toHaveBeenCalledTimes(1);
      const [body, options] = create.mock.calls[0] as [any, any];
      expect(body).toMatchObject({
        top_p: 0.9,
        n: 2,
        presence_penalty: 0.5,
        frequency_penalty: -0.5,
        logit_bias: { 1234: -100 },
        response_format: { type: 'json_object' },
        seed: 7,
        logprobs: true,
        top_logprobs: 3,
        stop: ['END', 'STOP'],
      });
      expect(body.messages).toEqual([
        { role: 'system', content: 'Be brief' },
        { role: 'user', content: 'Hello' },
      ]);
      expect(options).toEqual({ timeout: 30_000 });
    });

    it('forwards the abort signal and timeout as request options', async () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini', timeout: 5 });
      const create = await createMock(llm);
      const controller = new AbortController();
      await llm.generate('Hello', { signal: controller.signal });
      const [, options] = create.mock.calls[0] as [any, any];
      expect(options.signal).toBe(controller.signal);
      expect(options.timeout).toBe(5_000);
    });

    it('sends the wired fields with stream: true on generateStream()', async () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini', seed: 3, topP: 0.5 });
      const create = await createMock(llm);
      const tokens: string[] = [];
      for await (const token of llm.generateStream('Hello')) tokens.push(token);
      expect(tokens.join('')).toBe('Mock stream response');
      const [body] = create.mock.calls[0] as [any];
      expect(body).toMatchObject({ stream: true, seed: 3, top_p: 0.5 });
    });
  });

  describe('client wiring', () => {
    it('carries timeout (seconds -> ms) and apiVersion (api-version query) to the client', () => {
      const llm = new BaseLLM({
        model: 'gpt-4o-mini',
        apiKey: 'sk-test',
        baseURL: 'https://example.invalid/v1',
        timeout: 30,
        apiVersion: '2024-06-01',
      });
      expect(llm.buildClientOptions()).toMatchObject({
        apiKey: 'sk-test',
        baseURL: 'https://example.invalid/v1',
        timeout: 30_000,
        defaultQuery: { 'api-version': '2024-06-01' },
      });
    });

    it('omits timeout and api-version from client options when not set', () => {
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      const options = llm.buildClientOptions();
      expect(options).not.toHaveProperty('timeout');
      expect(options).not.toHaveProperty('defaultQuery');
    });
  });

  describe('parity notices', () => {
    it('reports nothing: every accepted option is honoured', () => {
      new BaseLLM(FULL_CONFIG);
      expect(unhonouredOptions()).toEqual([]);
    });

    it('reports nothing for Anthropic-only options on a Claude model', () => {
      new BaseLLM({
        model: 'claude-sonnet-4',
        promptCaching: true,
        webFetch: { max_uses: 3 },
        claudeMemory: true,
        events: [() => undefined],
        maxIter: 3,
        failoverManager: {},
        auth: () => ({ apiKey: 'sk' }),
      });
      expect(unhonouredOptions()).toEqual([]);
    });

    it('rejects Anthropic-only options on a non-Anthropic model instead of ignoring them', () => {
      expect(() => new BaseLLM({ model: 'gpt-4o-mini', webFetch: true })).toThrow(/webFetch.*Anthropic-style model/);
      expect(() => new BaseLLM({ model: 'gpt-4o-mini', claudeMemory: true })).toThrow(/claudeMemory.*Anthropic-style model/);
    });
  });
});
