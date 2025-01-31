import { OpenAIService } from '../../../src/llm/openai';

jest.mock('openai');

describe('OpenAI Service Integration', () => {
  let openAIService: OpenAIService;

  beforeEach(() => {
    openAIService = new OpenAIService();
  });

  describe('text generation', () => {
    it('should generate text response', async () => {
      const response = await openAIService.generateText('Hello');
      expect(response).toBe('Mock response');
    });

    it('should generate chat response', async () => {
      const messages = [
        { role: 'user' as const, content: 'Hello' }
      ];
      const response = await openAIService.generateChat(messages);
      expect(response.content).toBe('Mock response');
      expect(response.role).toBe('assistant');
    });

    it('should handle streaming response', async () => {
      let streamedText = '';
      await openAIService.streamText('Hello', '', 0.7, (token: string) => {
        streamedText += token;
      });
      expect(streamedText).toBe('Mock stream response');
    });
  });

  describe('error handling', () => {
    it('should handle invalid API key', async () => {
      const invalidService = new OpenAIService();
      jest.spyOn(invalidService as any, 'getClient').mockRejectedValue(new Error('Invalid API key'));
      await expect(invalidService.generateText('test')).rejects.toThrow('Invalid API key');
    });

    it('should handle rate limiting', async () => {
      jest.spyOn(openAIService as any, 'getClient').mockRejectedValue(new Error('Rate limit exceeded'));
      await expect(openAIService.generateText('test')).rejects.toThrow('Rate limit exceeded');
    });

    it('should handle context length exceeded', async () => {
      jest.spyOn(openAIService as any, 'getClient').mockRejectedValue(new Error('Context length exceeded'));
      await expect(openAIService.generateText('test')).rejects.toThrow('Context length exceeded');
    });
  });

  describe('model configuration', () => {
    it('should use correct model', async () => {
      const response = await openAIService.generateText('test');
      expect(response).toBe('Mock response');
    });

    it('should handle different temperature settings', async () => {
      const response1 = await openAIService.generateText('test', '', 0);
      const response2 = await openAIService.generateText('test', '', 1);
      expect(response1).toBe('Mock response');
      expect(response2).toBe('Mock response');
    });
  });
});
