# Praison AI

<iframe width="560" height="315" src="https://www.youtube.com/embed/Fn1lQjC0GO0" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>

<img alt="PraisonAI Logo" src="overrides/images/praisonai-logo-light.png" style="display: block; margin: auto;" />

<p align="center">
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://static.pepy.tech/badge/PraisonAI" alt="Total Downloads" /></a>
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://img.shields.io/github/v/release/MervinPraison/PraisonAI" alt="Latest Stable Version" /></a>
<a href="https://github.com/MervinPraison/PraisonAI"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License" /></a>
</p>

Praison AI, leveraging both AutoGen and CrewAI or any other agent framework, represents a low-code, centralised framework designed to simplify the creation and orchestration of multi-agent systems for various LLM applications, emphasizing ease of use, customization, and human-agent interaction.

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/architecture-dark.png" />
    <source media="(prefers-color-scheme: light)" srcset="images/architecture-light.png" />
    <img alt="PraisonAI Architecture" src="images/architecture-light.png" />
  </picture>
</div>

## Different User Interfaces:

| Interface | Description | URL |
|---|---|---|
| **UI** | Multi Agents such as CrewAI or AutoGen | [https://docs.praison.ai/ui/ui](https://docs.praison.ai/ui/ui) |
| **Chat** | Chat with 100+ LLMs, single AI Agent | [https://docs.praison.ai/ui/chat](https://docs.praison.ai/ui/chat) |
| **Code** | Chat with entire Codebase, single AI Agent | [https://docs.praison.ai/ui/code](https://docs.praison.ai/ui/code) |

## Google Colab Multi Agents

|               | Cookbook        | Open in Colab                                                                                                                                                                                                                                  |
| ------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Basic         | PraisonAI       | <a target="_blank" href="https://colab.research.google.com/github/MervinPraison/PraisonAI/blob/main/cookbooks/praisonai-googlecolab.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab" /></a>       |
| Include Tools | PraisonAI Tools | <a target="_blank" href="https://colab.research.google.com/github/MervinPraison/PraisonAI/blob/main/cookbooks/praisonai-tools-googlecolab.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab" /></a> |

## Install

| PraisonAI | PraisonAI Code | PraisonAI Chat |
| --- | --- | --- |
| `pip install praisonai` | `pip install "praisonai[code]"` | `pip install "praisonai[chat]"` |

## TL;DR Multi Agents

```bash
pip install praisonai
export OPENAI_API_KEY="Enter your API key"
praisonai --init create a movie script about dog in moon
praisonai
```

## Prerequisite:
### Export API KEY

```bash
export OPENAI_API_KEY="Enter your API key"
```

## Installation

```bash
pip install praisonai
```

## Automatically Create Agents to Perform a Task

```bash
praisonai --init create a movie script about dog in moon
```
## Run
```bash
praisonai
```
