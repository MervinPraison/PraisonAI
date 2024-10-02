# PraisonAI Chat

Use 100+ LLMs

## Different User Interfaces:

| Interface | Description | URL |
|---|---|---|
| **UI** | Multi Agents such as CrewAI or AutoGen | [https://docs.praison.ai/ui/ui](https://docs.praison.ai/ui/ui) |
| **Chat** | Chat with 100+ LLMs, single AI Agent | [https://docs.praison.ai/ui/chat](https://docs.praison.ai/ui/chat) |
| **Code** | Chat with entire Codebase, single AI Agent | [https://docs.praison.ai/ui/code](https://docs.praison.ai/ui/code) |

## Quick Start

1. Install PraisonAI Chat:
```bash
pip install "praisonai[chat]"
```

2. Set up your OpenAI API key:
```bash
export OPENAI_API_KEY=xxxxxxxx
```

3. Launch PraisonAI Chat:
```bash
praisonai chat
```
4. Set Model name to be gpt-4o-mini in the settings

## Key Features

### Internet Search

PraisonAI Chat now includes internet search capabilities using Crawl4AI and Tavily. This feature allows you to retrieve up-to-date information during your conversations, enhancing the AI's ability to provide current and relevant information.

### Vision Language Model (VLM) Support

You can now upload images and ask questions based on them using Vision Language Models. This multimodal support enables visual understanding and analysis within your chat sessions, allowing for a more comprehensive interaction with the AI.

To use this feature:
1. Upload an image to the chat interface
2. Ask questions or request analysis based on the uploaded image
3. The VLM will process the image and provide insights or answers based on its visual content

These new features significantly expand the capabilities of PraisonAI Chat, allowing for more diverse and informative interactions.