/**
 * A scriptable model double, so an agent can be tested offline.
 *
 * Python parity: `praisonaiagents.model_harness.scripted`
 * (`ScriptedModel`, `ScriptExhausted`).
 *
 * ```ts
 * const model = new ScriptedModel(['Refunded order A1.']);
 * const agent = new Agent({ instructions: 'Support bot.', llm: model });
 *
 * expect(await agent.chat('refund order A1')).toBe('Refunded order A1.');
 * expect(model.requestCount).toBe(1);
 * expect(model.requests[0].prompt).toBe('refund order A1');
 * ```
 *
 * Like the Python version, this subclasses the real {@link BaseLLM} and
 * replaces only the provider-facing methods, so prompt assembly, options
 * handling and the response shape all run production code. The double cannot
 * drift from the real client, because it *is* the real client with its network
 * boundary swapped out.
 */
import { BaseLLM, type LLMConfig, type LLMResponse, type LLMGenerateOptions } from '../llm';
import type {
  LLMProvider,
  GenerateTextOptions,
  GenerateTextResult,
  StreamTextOptions,
  StreamChunk,
  GenerateObjectOptions,
  GenerateObjectResult,
} from '../llm/providers/types';

/** Thrown when the script runs out of replies. */
export class ScriptExhausted extends Error {
  constructor(consumed: number, prompt: string) {
    super(
      `ScriptedModel ran out of replies after ${consumed}: the agent asked for another ` +
        `completion (prompt: ${JSON.stringify(prompt.slice(0, 120))}). Add a reply to the ` +
        `script, or assert that the agent stops earlier.`
    );
    this.name = 'ScriptExhausted';
  }
}

/** One request the agent actually sent, recorded for assertions. */
export interface RecordedRequest {
  prompt: string;
  systemPrompt?: string;
  options?: LLMGenerateOptions;
}

/** A scripted reply: a plain string, or a function of the request. */
export type ScriptEntry = string | ((request: RecordedRequest) => string);

export class ScriptedModel extends BaseLLM implements LLMProvider {
  private readonly script: ScriptEntry[];
  private cursor = 0;
  /** Every request the agent sent, in order. */
  readonly requests: RecordedRequest[] = [];

  constructor(script: ScriptEntry[], config: Partial<LLMConfig> = {}) {
    super({ model: config.model ?? 'scripted/test-model', ...config } as LLMConfig);
    this.script = [...script];
  }

  /** How many completions the agent asked for. */
  get requestCount(): number {
    return this.requests.length;
  }

  /** Replies left unconsumed. */
  get remaining(): number {
    return Math.max(0, this.script.length - this.cursor);
  }

  /** Rewind so the same instance can drive another run. */
  reset(): void {
    this.cursor = 0;
    this.requests.length = 0;
  }

  /** Append more replies to the script. */
  extend(...entries: ScriptEntry[]): void {
    this.script.push(...entries);
  }

  private next(request: RecordedRequest): string {
    this.requests.push(request);
    if (this.cursor >= this.script.length) {
      // Fail loudly rather than inventing a reply or hanging: a short script is
      // a test bug, and a silent default would make the assertion meaningless.
      throw new ScriptExhausted(this.cursor, request.prompt);
    }
    const entry = this.script[this.cursor++];
    return typeof entry === 'function' ? entry(request) : entry;
  }

  async generate(prompt: string, options?: LLMGenerateOptions): Promise<LLMResponse> {
    const text = this.next({ prompt, systemPrompt: options?.systemPrompt, options });
    return { text, metadata: { scripted: true, model: this.config.model } };
  }

  async *generateStream(
    prompt: string,
    options?: LLMGenerateOptions
  ): AsyncGenerator<string, void, unknown> {
    const text = this.next({ prompt, systemPrompt: options?.systemPrompt, options });
    yield text;
  }

  // -------------------------------------------------------------------------
  // LLMProvider: what Agent actually drives (via getBackend()). Implementing
  // both surfaces means the same double works for a direct model call and for
  // a full agent run.
  // -------------------------------------------------------------------------

  readonly providerId = 'scripted';

  get modelId(): string {
    return this.config.model ?? 'scripted/test-model';
  }

  /** The last user message, which is the prompt the agent is asking about. */
  private static lastUserText(options: GenerateTextOptions): string {
    for (let i = options.messages.length - 1; i >= 0; i--) {
      const m: any = options.messages[i];
      if (m?.role === 'user') return typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
    }
    return '';
  }

  private static systemText(options: GenerateTextOptions): string | undefined {
    const m: any = options.messages.find((x: any) => x?.role === 'system');
    return m ? (typeof m.content === 'string' ? m.content : JSON.stringify(m.content)) : undefined;
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    const text = this.next({
      prompt: ScriptedModel.lastUserText(options),
      systemPrompt: ScriptedModel.systemText(options),
    });
    return {
      text,
      usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      finishReason: 'stop',
    };
  }

  async streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    const result = await this.generateText(options);
    options.onToken?.(result.text);
    async function* once(): AsyncGenerator<StreamChunk> {
      yield { type: 'text', text: result.text } as unknown as StreamChunk;
    }
    return once();
  }

  async generateObject<T = any>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    const text = this.next({ prompt: ScriptedModel.lastUserText(options as any) });
    return {
      object: JSON.parse(text) as T,
      usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      finishReason: 'stop',
    } as GenerateObjectResult<T>;
  }

}
