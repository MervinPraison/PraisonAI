// Increase timeout for all tests
jest.setTimeout(10000);

// Unit suites mock the OpenAI SDK; provide a dummy key so client
// construction inside getOpenAIClient() doesn't reject before the mock
// is reached. Suites doing real API calls override this themselves.
if (!process.env.OPENAI_API_KEY) {
  process.env.OPENAI_API_KEY = 'test-key-not-real';
}

// Global test setup can go here
beforeAll(() => {
  // Setup any global test environment
});

afterAll(() => {
  // Cleanup any global test environment
});
