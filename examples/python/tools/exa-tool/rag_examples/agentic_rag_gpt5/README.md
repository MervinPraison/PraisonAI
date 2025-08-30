# 🧠 Agentic RAG with GPT-5

An agentic RAG application built with the PraisonAI Agents framework, featuring GPT-5 and built-in vector search for efficient knowledge retrieval and question answering.

## ✨ Features

- **🤖 GPT-5**: Latest OpenAI model for intelligent responses
- **🗄️ Built-in Vector Search**: ChromaDB integration for fast similarity search
- **🔍 Agentic RAG**: Intelligent retrieval augmented generation
- **📝 Markdown Formatting**: Beautiful, structured responses
- **🌐 Dynamic Knowledge**: Add URLs to expand knowledge base
- **⚡ Real-time Responses**: Fast answer generation- **🎯 Clean Interface**: Simplified UI without configuration complexity

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key with GPT-5 access

### Installation

1. **Clone and navigate to the project**
   ```bash
   cd rag_examples/agentic_rag_gpt5
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your OpenAI API key**
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```
   Or create a `.env` file:
   ```
   OPENAI_API_KEY=your-api-key-here
   ```

4. **Run the application**
   ```bash
   streamlit run agentic_rag_gpt5.py
   ```

## 🎯 How to Use

1. **Enter your OpenAI API key** in the sidebar
2. **Add knowledge sources** by entering URLs in the sidebar
3. **Ask questions** using the text area or suggested prompts
4. **Get answers** with markdown formatting

### Suggested Questions

- **"What is PraisonAI?"** - Learn about the PraisonAI Agents framework
- **"Teams in PraisonAI"** - Understand how teams work in PraisonAI
- **"Build RAG system"** - Get a step-by-step guide to building RAG systems

## 🏗️ Architecture

### Core Components

- **`Agent`**: PraisonAI Agents framework for intelligent Q&A
- **`knowledge`**: Built-in knowledge base that handles URLs and documents
- **`llm`**: OpenAI GPT-5-nano for generating responses
- **Built-in Vector Search**: Automatic similarity search without external setup

### Data Flow

1. **Knowledge Loading**: URLs are processed and stored in the built-in vector database
2. **Vector Search**: OpenAI embeddings enable semantic search
3. **Response Generation**: GPT-5-nano processes information and generates answers
4. **Formatted Output**: Markdown-formatted responses

## 🔧 Configuration

### Database Settings
- **Vector DB**: Built-in vector database with automatic indexing
- **Storage**: Local storage managed by PraisonAI Agents
- **Search**: Automatic similarity search

### Model Configuration
- **LLM**: OpenAI GPT-5-nano
- **Embeddings**: Automatic handling by PraisonAI Agents
- **Vector Store**: Built-in with automatic document processing

## 📚 Knowledge Management

### Adding Sources
- Use the sidebar to add new URLs
- Sources are automatically processed and indexed
- Current sources are displayed as numbered list

### Default Knowledge
- Starts with PraisonAI documentation: `https://docs.praisonai.com/introduction/agents.md`
- Expandable with any web-based documentation

## 🎨 UI Features

### Sidebar
- **API Key Management**: Secure input for OpenAI credentials
- **URL Addition**: Dynamic knowledge base expansion
- **Current Sources**: Numbered list of loaded URLs

### Main Interface
- **Suggested Prompts**: Quick access to common questions
- **Query Input**: Large text area for custom questions
- **Fast Responses**: Quick answer generation
- **Markdown Rendering**: Beautiful formatted responses

## 🛠️ Technical Details

### Dependencies
```
streamlit>=1.28.0
praisonaiagents>=0.1.0
openai>=1.0.0
python-dotenv>=1.0.0
```

### Key Features
- **Built-in Knowledge Base**: Automatic document processing and indexing
- **Vector Search**: Efficient similarity search with built-in database
- **Caching**: Efficient resource loading with Streamlit caching
- **Error Handling**: Graceful handling of API and processing errors

## 🔍 Troubleshooting

### Common Issues

**Knowledge base not loading**
- Check OpenAI API key is valid
- Ensure URLs are accessible
- Verify internet connection

**Agent initialization errors**
- Check if PraisonAI Agents is properly installed
- Verify OpenAI API key has sufficient credits
- Ensure Python version is 3.11+

### Performance Tips
- **Cache Resources**: Knowledge base and agent are cached for efficiency
- **Built-in Vector Search**: Fast similarity search without external setup
- **Local Storage**: Optimized local storage for optimal performance

## 🎯 Use Cases

- **Documentation Q&A**: Ask questions about technical documentation
- **Research Assistant**: Get answers from multiple knowledge sources
- **Learning Tool**: Interactive exploration of complex topics
- **Content Discovery**: Find relevant information across multiple sources

**Built with ❤️ using PraisonAI Agents and GPT-5**
