# Módulo: Modelos de LLM no PraisonAI

Um dos pontos fortes do PraisonAI é sua flexibilidade em relação aos Modelos de Linguagem Grande (LLMs). Ele não está restrito a um único provedor e é projetado para suportar uma variedade de LLMs, incluindo modelos da OpenAI, modelos locais via Ollama, inferência rápida com Groq, modelos do Google Gemini, e muitos outros (PraisonAI menciona "100+ LLM Support").

Esta flexibilidade permite que você escolha o LLM que melhor se adapta às suas necessidades em termos de custo, performance, capacidades específicas, ou requisitos de privacidade (no caso de modelos locais).

## Configuração Geral de LLMs

A forma como você configura um LLM no PraisonAI geralmente envolve duas etapas:

1.  **Configuração do Provedor (Variáveis de Ambiente):**
    Muitos provedores de LLM exigem chaves de API e, às vezes, URLs base específicas. Estas são comumente configuradas através de variáveis de ambiente.

2.  **Especificação no Agente:**
    Ao definir um [Agente](./../02_conceitos_fundamentais/01_agentes.md), você pode especificar qual modelo ou provedor ele deve usar. Se não especificado, o PraisonAI pode usar um padrão (frequentemente um modelo OpenAI como GPT-3.5 Turbo).

## Configurando Provedores Comuns

Vamos ver como configurar alguns dos provedores de LLM mais populares para uso com o PraisonAI:

### 1. OpenAI (GPT-3.5, GPT-4, etc.)

*   **Variável de Ambiente Principal:**
    ```bash
    export OPENAI_API_KEY="sua_chave_api_da_openai_aqui"
    ```
    (No Windows, use `set` ou `setx` ou a interface gráfica, conforme detalhado no [Guia de Instalação](./../01_instalacao/00_instalacao_windows.md)).
*   **Uso:** Esta é geralmente a configuração padrão ou mais direta no PraisonAI.

### 2. Ollama (Modelos Locais como Llama, Mistral, etc.)

Ollama permite que você execute LLMs de código aberto localmente na sua máquina. O PraisonAI pode interagir com o servidor Ollama através de uma API compatível com a API da OpenAI.

*   **Pré-requisito:** Ter o Ollama instalado e rodando. (Veja [ollama.com](https://ollama.com/)). Certifique-se de ter baixado os modelos que deseja usar (ex: `ollama pull llama3`).
*   **Variáveis de Ambiente:**
    ```bash
    # URL onde seu servidor Ollama está escutando (padrão)
    export OPENAI_BASE_URL="http://localhost:11434/v1"

    # A API do Ollama pode ou não exigir uma chave, mas é comum manter o padrão da API OpenAI.
    # Você pode usar um valor fictício se o modelo específico não exigir autenticação.
    export OPENAI_API_KEY="ollama" # ou "EMPTY", ou sua chave real se configurou uma no Ollama

    # (Opcional, mas recomendado) Especifique o nome do modelo que o Ollama deve usar por padrão,
    # se não for especificado no agente.
    # export OPENAI_MODEL_NAME="llama3:latest"
    ```
*   **Especificação do Modelo no Agente:** Ao definir um agente, você precisará informar o nome do modelo Ollama que deseja usar (ex: `llama3:latest`, `mistral:latest`).

### 3. Groq (Inferência Rápida)

Groq fornece inferência de LLM em alta velocidade usando seus LPUs (Language Processing Units).

*   **Pré-requisito:** Ter uma chave de API do Groq (veja [groq.com](https://groq.com/)).
*   **Variáveis de Ambiente:**
    ```bash
    # URL da API do Groq (compatível com OpenAI)
    export OPENAI_BASE_URL="https://api.groq.com/openai/v1"

    # Sua chave de API específica do Groq
    export OPENAI_API_KEY="sua_chave_api_do_groq_aqui"
    ```
*   **Especificação do Modelo no Agente:** Você usará os nomes dos modelos disponíveis no Groq (ex: `llama3-8b-8192`, `mixtral-8x7b-32768`).

### 4. Google Gemini

*   **Pré-requisito:** Ter uma chave de API do Google AI Studio ou configurado para usar Gemini via Vertex AI no Google Cloud.
*   **Variáveis de Ambiente:** A configuração exata pode variar (ex: `GOOGLE_API_KEY`). O PraisonAI pode ter um manipulador específico para Gemini.
*   **Recomendação:** Consulte a documentação oficial do PraisonAI ou exemplos específicos sobre como integrar modelos Gemini, pois pode haver um fluxo de configuração um pouco diferente do padrão `OPENAI_*`.

### 5. Outros Modelos (Anthropic Claude, Cohere, etc.)

PraisonAI visa suportar uma ampla gama de modelos. A configuração para cada um pode envolver:
*   Variáveis de ambiente específicas (ex: `ANTHROPIC_API_KEY`).
*   Uso de URLs base específicas se eles expõem uma API compatível com OpenAI.
*   Manipuladores (handlers) ou clientes específicos dentro do PraisonAI para esses modelos.

> [!IMPORTANT]
> A lista de modelos suportados e seus métodos de configuração exatos podem evoluir. **Sempre consulte a documentação oficial do PraisonAI (`https://docs.praison.ai/models`) para as informações mais atualizadas.**

## Especificando o Modelo no Agente

Uma vez que o provedor está configurado através das variáveis de ambiente, você pode (e muitas vezes deve) especificar qual modelo exato um agente deve usar.

*   **Em YAML:**
    Dentro da definição de um `role` (agente), você pode adicionar uma seção `llm` ou `model`:
    ```yaml
    roles:
      escritor_rapido:
        role: "Escritor Rápido"
        goal: "Gerar texto rapidamente para tarefas simples."
        # Exemplo para Groq
        llm:
          provider: groq # Ou openai, ollama, etc. (o nome do provider pode variar)
          model: "llama3-8b-8192"
          # temperature: 0.6 # Outros parâmetros do LLM
        # Exemplo para Ollama (o nome do modelo geralmente inclui o registry/tag)
        # llm:
        #   model: "ollama/llama3:latest" # A sintaxe exata pode variar
        # Ou mais simples se OPENAI_BASE_URL e OPENAI_MODEL_NAME estiverem configurados para Ollama:
        # llm:
        #   model: "llama3:latest" # Se o provider é inferido como OpenAI-compatible
        # ...
      analista_profundo:
        role: "Analista Detalhista"
        goal: "Realizar análises complexas e profundas."
        llm:
          provider: openai
          model: "gpt-4-turbo-preview"
          temperature: 0.3
        # ...
    ```
    *A estrutura exata da seção `llm` (ex: `provider`, `model`) pode depender da versão do PraisonAI e do framework subjacente (`praisonai`, `crewai`, `autogen`). Verifique os exemplos YAML no repositório.*

*   **Em Python:**
    Ao instanciar um `Agent`, você pode passar um objeto de configuração do LLM ou o nome do modelo.
    ```python
    from praisonaiagents import Agent
    # Supondo que existam classes ou formas de configurar LLMs específicos
    # from praisonai.llms import Ollama # Exemplo conceitual

    # Exemplo para OpenAI (muitas vezes o padrão, mas pode ser explícito)
    # agente_openai = Agent(
    #     role="Assistente GPT",
    #     goal="Usar GPT-4.",
    #     llm={"model": "gpt-4"} # A forma de passar pode variar
    # )

    # Exemplo para Ollama (conceitual)
    # llm_ollama_config = Ollama(model="llama3:latest", base_url="http://localhost:11434")
    # agente_ollama = Agent(
    #     role="Assistente Llama Local",
    #     goal="Usar Llama 3 localmente via Ollama.",
    #     llm=llm_ollama_config # Passando o objeto LLM configurado
    # )

    # Outra forma comum, se o PraisonAI usa uma API compatível com OpenAI para Ollama/Groq:
    # (Com OPENAI_BASE_URL e OPENAI_API_KEY configurados para Ollama)
    agente_ollama_openai_api = Agent(
        role="Assistente Local (API OpenAI)",
        goal="Usar modelo Ollama através da API compatível.",
        llm={"model": "llama3:latest"} # O nome do modelo Ollama
        # PraisonAI usaria OPENAI_BASE_URL para direcionar para Ollama
    )
    ```
    *A API Python para configurar LLMs específicos pode ser bastante rica. Consulte os exemplos em `examples/python/models/` e a documentação da API `praisonaiagents`.*

## Considerações

*   **Compatibilidade de Recursos:** Nem todos os LLMs suportam todos os recursos da mesma forma (ex: "function calling"/"tool using", multimodalidade, tamanho da janela de contexto). Escolha o modelo também com base nos recursos que seus agentes precisam.
*   **Custos:** Esteja ciente dos custos associados a cada provedor de LLM. Modelos mais poderosos geralmente são mais caros.
*   **Desempenho (Latência e Qualidade):** Diferentes modelos têm diferentes características de latência e qualidade de resposta. Teste para encontrar o equilíbrio certo para sua aplicação.
*   **Nomes dos Modelos:** Os nomes exatos dos modelos (`gpt-3.5-turbo`, `llama3:latest`, `mixtral-8x7b-32768`, etc.) devem corresponder ao que o provedor espera.

A capacidade do PraisonAI de se integrar com uma ampla gama de LLMs é uma vantagem significativa, permitindo que você adapte seus agentes às melhores ferramentas de linguagem disponíveis para cada tarefa.
