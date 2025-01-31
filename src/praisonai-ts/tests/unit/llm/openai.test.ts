import { OpenAIService } from '../../../src/llm/openai';

jest.mock('openai');

describe('OpenAIService', () => {
  let openAIService: OpenAIService;

  beforeEach(() => {
    openAIService = new OpenAIService();
  });

  describe('text generation', () => {
    it('should generate text with default settings', async () => {
      const prompt = 'Hello, how are you?';
      const response = await openAIService.generateText(prompt);
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

    it('should handle errors gracefully', async () => {
      const mockError = new Error('API Error');
      jest.spyOn(openAIService as any, 'getClient').mockRejectedValue(mockError);

      await expect(openAIService.generateText('test')).rejects.toThrow('API Error');
    });
  });
});
