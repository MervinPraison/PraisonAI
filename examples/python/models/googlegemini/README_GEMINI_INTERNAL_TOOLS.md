# Gemini Internal Tools Examples

This directory contains examples demonstrating how to use Google Gemini's built-in internal tools through PraisonAI. These tools are natively supported by Gemini models and provide powerful capabilities without requiring external tool implementations.

## Available Internal Tools

### 1. Google Search (`googleSearch`)
- **Purpose**: Real-time web search with automatic result grounding
- **Use Cases**: Current events, latest information, fact-checking
- **Example**: `gemini-google-search.py`

### 2. URL Context (`urlContext`) 
- **Purpose**: Fetch and analyze content from specific URLs
- **Use Cases**: Document analysis, web content summarization, research
- **Example**: `gemini-url-context.py`

### 3. Code Execution (`codeExecution`)
- **Purpose**: Execute Python code snippets within the conversation
- **Use Cases**: Calculations, data analysis, code validation
- **Example**: `gemini-code-execution.py`

## Prerequisites

1. **Gemini API Key**: Set your Google AI Studio API key
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```

2. **Compatible Model**: Use Gemini models that support internal tools:
   - `gemini/gemini-2.0-flash` (recommended)
   - `gemini/gemini-2.0-flash-thinking-exp`
   - Other Gemini 2.0+ models

3. **PraisonAI Installation**: Ensure you have the latest version
   ```bash
   pip install praisonaiagents
   ```

## Examples

### Individual Tool Examples

1. **Google Search Example** (`gemini-google-search.py`)
   ```python
   agent = Agent(
       instructions="Research assistant with web search",
       llm="gemini/gemini-2.0-flash",
       tools=[{"googleSearch": {}}]
   )
   
   response = agent.start("What's the latest news about AI?")
   ```

2. **URL Context Example** (`gemini-url-context.py`)
   ```python
   agent = Agent(
       instructions="Content analyzer",
       llm="gemini/gemini-2.0-flash", 
       tools=[{"urlContext": {}}]
   )
   
   response = agent.start("Summarize this: https://example.com/article")
   ```

3. **Code Execution Example** (`gemini-code-execution.py`)
   ```python
   agent = Agent(
       instructions="Data analyst with code execution",
       llm="gemini/gemini-2.0-flash",
       tools=[{"codeExecution": {}}]
   )
   
   response = agent.start("Calculate compound interest for $10,000 at 5% for 10 years")
   ```

### Combined Tools Example

**All Tools Together** (`gemini-internal-tools-combined.py`)
```python
agent = Agent(
    instructions="Advanced research assistant",
    llm="gemini/gemini-2.0-flash",
    tools=[
        {"googleSearch": {}},
        {"urlContext": {}},
        {"codeExecution": {}}
    ]
)

# Now the agent can search, analyze URLs, and execute code as needed
```

## How It Works

### PraisonAI Integration

PraisonAI's tool system is designed to pass tools directly to LiteLLM without modification:

1. **Tool Definition**: Define tools using the special internal tool syntax
   ```python
   tools=[{"googleSearch": {}}]  # Special format for internal tools
   ```

2. **Pass-Through**: PraisonAI passes these tools directly to LiteLLM
3. **Execution**: LiteLLM sends them to Gemini as internal tool configurations
4. **Results**: Gemini executes the tools natively and returns integrated responses

### Mixing with External Tools

You can combine internal tools with custom external tools:

```python
def custom_calculator(expression: str) -> str:
    """Custom calculator function"""
    return str(eval(expression))

agent = Agent(
    tools=[
        {"googleSearch": {}},      # Internal tool
        {"codeExecution": {}},     # Internal tool  
        custom_calculator          # External tool
    ]
)
```

## Running the Examples

1. **Set API Key**:
   ```bash
   export GEMINI_API_KEY="your-api-key"
   ```

2. **Run Individual Examples**:
   ```bash
   python gemini-google-search.py
   python gemini-url-context.py  
   python gemini-code-execution.py
   ```

3. **Run Combined Example**:
   ```bash
   python gemini-internal-tools-combined.py
   ```

## Benefits Over External Tools

### Advantages of Internal Tools

1. **Native Integration**: No need to implement or maintain external tool code
2. **Optimized Performance**: Tools are executed within Gemini's environment
3. **Automatic Grounding**: Search results are automatically integrated into responses
4. **No Rate Limits**: No separate API calls or rate limiting concerns
5. **Security**: Code execution is sandboxed within Gemini's environment

### When to Use External Tools

- When you need specific custom logic
- When you require integration with private APIs
- When you need persistent data storage
- When you want full control over tool behavior

## Troubleshooting

### Common Issues

1. **API Key Error**: Ensure `GEMINI_API_KEY` is set correctly
2. **Model Not Supported**: Use Gemini 2.0+ models for internal tools
3. **Tool Not Available**: Some tools may have regional or quota restrictions

### Debug Mode

Enable verbose logging to see tool usage:
```python
agent = Agent(
    # ... config
    verbose=True  # Shows detailed tool usage
)
```

## References

- [Gemini API: Google Search Grounding](https://ai.google.dev/gemini-api/docs/google-search)
- [Gemini API: URL Context](https://ai.google.dev/gemini-api/docs/url-context)  
- [Gemini API: Code Execution](https://ai.google.dev/gemini-api/docs/code-execution)
- [LiteLLM Gemini Provider Documentation](https://docs.litellm.ai/docs/providers/gemini)

## Contributing

If you create additional examples or find improvements, please contribute back to the PraisonAI project!