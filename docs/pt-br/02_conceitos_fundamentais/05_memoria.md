# Conceito Fundamental: Memória (Memory)

Para que os [Agentes](./01_agentes.md) do PraisonAI tenham conversas coerentes, aprendam com interações passadas e mantenham o contexto ao longo de [Tarefas](./02_tarefas.md) complexas, eles precisam de **Memória (Memory)**. A memória é um componente crucial que eleva os agentes de simples processadores de comandos para assistentes mais inteligentes e contextuais.

## O que é Memória para Agentes de IA?

No contexto de Agentes de IA e LLMs, Memória refere-se à capacidade do sistema de **armazenar, reter e recuperar informações de interações ou experiências passadas**. Sem memória, cada interação com um agente seria isolada, e o agente não teria conhecimento do que foi dito ou feito anteriormente.

**Tipos Comuns de Memória em Agentes:**

1.  **Memória de Curto Prazo (Short-Term Memory):**
    *   **Propósito:** Manter o contexto da conversa ou sessão atual. É como a "memória de trabalho" de um humano.
    *   **Implementação Comum:** Armazenar um histórico das últimas N interações (perguntas e respostas) e fornecê-lo como parte do prompt para o LLM a cada nova interação. Isso é frequentemente chamado de "janela de contexto deslizante" (sliding context window).
    *   **Limitações:** O tamanho da janela de contexto dos LLMs é finito. Para conversas muito longas, informações mais antigas podem ser perdidas.

2.  **Memória de Longo Prazo (Long-Term Memory):**
    *   **Propósito:** Permitir que o agente retenha informações importantes, fatos aprendidos, preferências do usuário ou resumos de conversas passadas por um período indefinido.
    *   **Implementação Comum:**
        *   **Bancos de Dados Vetoriais (Vector Databases):** Informações textuais são convertidas em embeddings (vetores numéricos) e armazenadas. Quando necessário, a pergunta atual do usuário ou o contexto da tarefa é usado para buscar semanticamente informações relevantes no banco de dados vetorial. O PraisonAI menciona integração com Mem0, que é um exemplo de memória de longo prazo inteligente.
        *   **Bancos de Dados Tradicionais (SQL, NoSQL):** Para armazenar dados estruturados ou semi-estruturados sobre o usuário ou o domínio.
        *   **Resumos de Conversas:** Agentes podem ser programados para resumir conversas periodicamente e armazenar esses resumos na memória de longo prazo.

## Memória no PraisonAI

PraisonAI enfatiza a importância da memória para seus agentes, listando "Agentes com Memória de Curto e Longo Prazo" como um recurso chave.

### Como o PraisonAI Implementa a Memória

A implementação específica pode variar dependendo da configuração e dos componentes usados, mas geralmente envolve:

*   **Gerenciamento Automático de Histórico (Curto Prazo):** O framework provavelmente lida com o histórico da conversa atual, enviando-o ao LLM conforme necessário, dentro dos limites da janela de contexto do modelo.

*   **Integração com Sistemas de Memória Externa (Longo Prazo):**
    *   **Bancos de Dados Vetoriais:** Para buscas semânticas e recuperação de informações relevantes de um grande corpus de dados ou de conversas passadas. Exemplos de Vector DBs incluem Pinecone, Weaviate, ChromaDB, FAISS.
    *   **Mem0:** O PraisonAI menciona especificamente a integração com [Mem0](https://mem0.ai/), uma plataforma de memória inteligente como serviço (MaaS) projetada para LLMs, que visa fornecer memória persistente e contextual de forma eficiente.
    *   **Outras Soluções:** Pode incluir o uso de bancos de dados relacionais ou NoSQL para armazenar perfis de usuário, preferências ou outros dados estruturados que o agente precise lembrar.

### Configurando e Usando a Memória

*   **Programaticamente (Python):**
    Ao definir um agente ou um "crew" (time de agentes), você pode configurar o tipo de memória a ser usado.
    \`\`\`python
    from praisonaiagents import Agent # ou de onde vier a classe Agent
    # from praisonai.memory import AlgumModuloDeMemoria # Exemplo conceitual

    # Exemplo conceitual de como a memória poderia ser atribuída
    agente_com_memoria = Agent(
        role="Assistente Pessoal",
        goal="Lembrar minhas preferências e histórico de pedidos.",
        # ...
        memory=True, # Habilita a memória padrão (curto prazo)
        # long_term_memory_handler=MeuHandlerDeMemoriaMem0(), # Exemplo para longo prazo
        # vector_database_config={...} # Outra forma de configurar
    )

    # O agente usaria a memória automaticamente ao processar tarefas
    # agente_com_memoria.start("Lembre-se que minha cor favorita é azul.")
    # agente_com_memoria.start("Qual é a minha cor favorita?")
    \`\`\`
    > A sintaxe exata e as opções de configuração da memória podem ser encontradas nos exemplos do PraisonAI, como `examples/python/general/memory_example.py` ou `memory_simple.py`, e na documentação da API.

*   **Declarativamente (YAML):**
    Em arquivos YAML, pode haver seções ou propriedades para configurar a memória dos agentes ou do workflow.
    \`\`\`yaml
    # Exemplo conceitual em YAML
    roles:
      assistente_pessoal:
        role: Assistente Pessoal
        goal: Lembrar preferências e histórico.
        memory:
          enabled: true
          type: mem0 # ou 'vector_db', 'short_term_default'
          # config: # Configurações específicas para o tipo de memória
          #   api_key: "sua_chave_mem0_aqui"
          #   user_id: "usuario123"
        # ...
    \`\`\`

### O Diagrama "AI Agents with Memory" do README

O `README.md` principal do PraisonAI inclui um diagrama útil:

\`\`\`mermaid
flowchart TB
    subgraph Memoria ["Memoria"]
        direction TB
        MCP["Curto Prazo"]
        MLP["Longo Prazo"]
    end
    subgraph Armazenamento ["Armazenamento"]
        direction TB
        BD["(Vector DB)"]
    end
    Entrada["Entrada"] ---> Agentes
    subgraph Agentes
        direction LR
        A1["Agente 1"]
        A2["Agente 2"]
        A3["Agente 3"]
    end
    Agentes ---> Saida["Saida"]
    Memoria <--> Armazenamento
    Armazenamento <--> A1
    Armazenamento <--> A2
    Armazenamento <--> A3
    style Memoria fill:#189AB4,color:#fff
    style Armazenamento fill:#2E8B57,color:#fff
    style Agentes fill:#8B0000,color:#fff
    style Entrada fill:#8B0000,color:#fff
    style Saida fill:#8B0000,color:#fff
\`\`\`
*   **Interpretação:**
    *   Os **Agentes** recebem uma **Entrada**.
    *   Eles têm acesso à **Memória**, que é dividida em **Curto Prazo** e **Longo Prazo**.
    *   A **Memória de Longo Prazo** é frequentemente suportada por um **Armazenamento** externo, como um **Banco de Dados Vetorial (Vector DB)**.
    *   Há uma interação bidirecional entre a Memória e o Armazenamento (dados são salvos e recuperados).
    *   Os Agentes também interagem bidirecionalmente com o Armazenamento (ou com a camada de Memória que gerencia o armazenamento).
    *   Com base na entrada e nas informações recuperadas da memória, os Agentes produzem uma **Saída**.

## Fundamentos por Trás

*   **Psicologia Cognitiva:** Os conceitos de memória de curto e longo prazo em IA são inspirados em modelos da memória humana.
*   **Recuperação de Informação (Information Retrieval):** Técnicas para buscar eficientemente dados relevantes em grandes armazenamentos, especialmente buscas semânticas usando embeddings.
*   **Gerenciamento de Contexto:** Estratégias para manter o fluxo da conversa e fornecer ao LLM as informações necessárias para gerar respostas relevantes e coerentes.

Uma memória eficaz é o que permite aos agentes PraisonAI construir relacionamentos de longo prazo com os usuários, aprender com as interações e realizar tarefas complexas que exigem a lembrança de informações ao longo do tempo.

O próximo conceito fundamental é **Conhecimento (Knowledge)** e como ele se relaciona com RAG (Retrieval Augmented Generation).
