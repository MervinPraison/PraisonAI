/**
 * Slack Integration
 * 
 * Provides Slack bot adapters for building AI-powered Slack bots.
 */

export interface SlackConfig {
  /** Slack Bot Token (xoxb-...) */
  botToken: string;
  /** Slack App Token for Socket Mode (xapp-...) */
  appToken?: string;
  /** Slack Signing Secret for webhook verification */
  signingSecret?: string;
  /** Enable Socket Mode (default: false, uses webhooks) */
  socketMode?: boolean;
}

export interface SlackMessage {
  /** Channel ID */
  channel: string;
  /** User ID */
  user: string;
  /** Message text */
  text: string;
  /** Thread timestamp (for replies) */
  threadTs?: string;
  /** Message timestamp */
  ts: string;
  /** Bot ID (if from a bot) */
  botId?: string;
}

export interface SlackResponse {
  /** Response text */
  text: string;
  /** Blocks for rich formatting */
  blocks?: any[];
  /** Thread timestamp (to reply in thread) */
  threadTs?: string;
  /** Unfurl links */
  unfurlLinks?: boolean;
  /** Unfurl media */
  unfurlMedia?: boolean;
}

export interface SlackEventHandler {
  /** Handle a message event */
  onMessage: (message: SlackMessage) => Promise<SlackResponse | null>;
  /** Handle an app mention event */
  onAppMention?: (message: SlackMessage) => Promise<SlackResponse | null>;
  /** Handle a reaction added event */
  onReactionAdded?: (event: any) => Promise<void>;
}

/**
 * Create a Slack bot adapter.
 * 
 * @example Basic usage
 * ```typescript
 * import { createSlackBot } from 'praisonai/integrations/slack';
 * import { Agent } from 'praisonai';
 * 
 * const agent = new Agent({ instructions: 'You are a helpful Slack bot' });
 * 
 * const bot = createSlackBot({
 *   botToken: process.env.SLACK_BOT_TOKEN!,
 *   signingSecret: process.env.SLACK_SIGNING_SECRET!
 * });
 * 
 * bot.onMessage(async (message) => {
 *   const response = await agent.chat(message.text);
 *   return { text: response, threadTs: message.ts };
 * });
 * 
 * // Start webhook server
 * bot.listen(3000);
 * ```
 * 
 * @example With Socket Mode
 * ```typescript
 * const bot = createSlackBot({
 *   botToken: process.env.SLACK_BOT_TOKEN!,
 *   appToken: process.env.SLACK_APP_TOKEN!,
 *   socketMode: true
 * });
 * 
 * bot.onMessage(async (message) => {
 *   return { text: 'Hello!' };
 * });
 * 
 * await bot.start();
 * ```
 */
export function createSlackBot(config: SlackConfig): SlackBot {
  return new SlackBot(config);
}

export class SlackBot {
  private config: SlackConfig;
  private messageHandler?: (message: SlackMessage) => Promise<SlackResponse | null>;
  private mentionHandler?: (message: SlackMessage) => Promise<SlackResponse | null>;
  private reactionHandler?: (event: any) => Promise<void>;
  private boltApp: any = null;

  constructor(config: SlackConfig) {
    this.config = config;
  }

  /**
   * Set the message handler.
   */
  onMessage(handler: (message: SlackMessage) => Promise<SlackResponse | null>): this {
    this.messageHandler = handler;
    return this;
  }

  /**
   * Set the app mention handler.
   */
  onAppMention(handler: (message: SlackMessage) => Promise<SlackResponse | null>): this {
    this.mentionHandler = handler;
    return this;
  }

  /**
   * Set the reaction handler.
   */
  onReactionAdded(handler: (event: any) => Promise<void>): this {
    this.reactionHandler = handler;
    return this;
  }

  /**
   * Initialize the Bolt app (lazy load).
   */
  private async initBolt(): Promise<any> {
    if (this.boltApp) return this.boltApp;

    try {
      // @ts-ignore - Optional dependency
      const { App } = await import('@slack/bolt');
      
      this.boltApp = new App({
        token: this.config.botToken,
        signingSecret: this.config.signingSecret,
        appToken: this.config.appToken,
        socketMode: this.config.socketMode,
      });

      // Register message handler
      if (this.messageHandler) {
        this.boltApp.message(async ({ message, say }: any) => {
          // Skip bot messages
          if (message.bot_id) return;

          const slackMessage: SlackMessage = {
            channel: message.channel,
            user: message.user,
            text: message.text || '',
            threadTs: message.thread_ts,
            ts: message.ts,
          };

          const response = await this.messageHandler!(slackMessage);
          if (response) {
            await say({
              text: response.text,
              blocks: response.blocks,
              thread_ts: response.threadTs || message.ts,
              unfurl_links: response.unfurlLinks,
              unfurl_media: response.unfurlMedia,
            });
          }
        });
      }

      // Register app mention handler
      if (this.mentionHandler) {
        this.boltApp.event('app_mention', async ({ event, say }: any) => {
          const slackMessage: SlackMessage = {
            channel: event.channel,
            user: event.user,
            text: event.text || '',
            threadTs: event.thread_ts,
            ts: event.ts,
          };

          const response = await this.mentionHandler!(slackMessage);
          if (response) {
            await say({
              text: response.text,
              blocks: response.blocks,
              thread_ts: response.threadTs || event.ts,
            });
          }
        });
      }

      // Register reaction handler
      if (this.reactionHandler) {
        this.boltApp.event('reaction_added', async ({ event }: any) => {
          await this.reactionHandler!(event);
        });
      }

      return this.boltApp;
    } catch (error: any) {
      throw new Error(
        `Failed to initialize Slack Bolt: ${error.message}. ` +
        'Install with: npm install @slack/bolt'
      );
    }
  }

  /**
   * Start the bot (Socket Mode).
   */
  async start(): Promise<void> {
    const app = await this.initBolt();
    await app.start();
    console.log('⚡️ Slack bot is running in Socket Mode');
  }

  /**
   * Start webhook server.
   */
  async listen(port: number = 3000): Promise<void> {
    const app = await this.initBolt();
    await app.start(port);
    console.log(`⚡️ Slack bot is running on port ${port}`);
  }

  /**
   * Stop the bot.
   */
  async stop(): Promise<void> {
    if (this.boltApp) {
      await this.boltApp.stop();
    }
  }

  /**
   * Send a message to a channel.
   */
  async sendMessage(channel: string, text: string, options?: Partial<SlackResponse>): Promise<void> {
    const app = await this.initBolt();
    await app.client.chat.postMessage({
      token: this.config.botToken,
      channel,
      text,
      blocks: options?.blocks,
      thread_ts: options?.threadTs,
      unfurl_links: options?.unfurlLinks,
      unfurl_media: options?.unfurlMedia,
    });
  }

  /**
   * Get an Express middleware for webhook handling.
   */
  getExpressMiddleware(): any {
    return async (req: any, res: any, next: any) => {
      const app = await this.initBolt();
      return app.receiver.app(req, res, next);
    };
  }
}

/**
 * Verify Slack request signature.
 */
export function verifySlackSignature(
  signingSecret: string,
  signature: string,
  timestamp: string,
  body: string
): boolean {
  const crypto = require('crypto');
  const baseString = `v0:${timestamp}:${body}`;
  const hmac = crypto.createHmac('sha256', signingSecret);
  hmac.update(baseString);
  const computedSignature = `v0=${hmac.digest('hex')}`;
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(computedSignature)
  );
}

/**
 * Parse Slack message text to extract mentions and links.
 */
export function parseSlackMessage(text: string): {
  mentions: string[];
  links: string[];
  cleanText: string;
} {
  const mentions: string[] = [];
  const links: string[] = [];
  
  // Extract user mentions <@U123456>
  const mentionRegex = /<@([A-Z0-9]+)>/g;
  let match;
  while ((match = mentionRegex.exec(text)) !== null) {
    mentions.push(match[1]);
  }
  
  // Extract links <http://...|label>
  const linkRegex = /<(https?:\/\/[^|>]+)(?:\|[^>]+)?>/g;
  while ((match = linkRegex.exec(text)) !== null) {
    links.push(match[1]);
  }
  
  // Clean text (remove mentions and format links)
  const cleanText = text
    .replace(/<@[A-Z0-9]+>/g, '')
    .replace(/<(https?:\/\/[^|>]+)(?:\|([^>]+))?>/g, '$2 ($1)')
    .trim();
  
  return { mentions, links, cleanText };
}
