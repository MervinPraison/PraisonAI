const mockChatCompletion = {
  choices: [{
    message: {
      content: 'Mock response',
      role: 'assistant'
    }
  }]
};

const mockStreamResponse = {
  [Symbol.asyncIterator]: () => {
    const chunks = [
      { choices: [{ delta: { content: 'Mock ' } }] },
      { choices: [{ delta: { content: 'stream ' } }] },
      { choices: [{ delta: { content: 'response' } }] }
    ];
    let index = 0;
    return {
      next: async () => {
        if (index < chunks.length) {
          return { value: chunks[index++], done: false };
        }
        return { value: undefined, done: true };
      }
    };
  }
};

export default class OpenAI {
  constructor(config: any) {
    // Mock constructor
  }

  chat = {
    completions: {
      create: jest.fn().mockImplementation((options: any) => {
        if (options.stream) {
          return mockStreamResponse;
        }
        return Promise.resolve(mockChatCompletion);
      })
    }
  };

  completions = {
    create: jest.fn().mockResolvedValue({
      choices: [{
        text: 'Mock response'
      }]
    })
  };
}
