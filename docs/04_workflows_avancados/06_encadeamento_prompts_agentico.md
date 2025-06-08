# TODO: Translate this file to English

# Workflows Avançados: Encadeamento de Prompts Agêntico (Agentic Prompt Chaining)

O **Encadeamento de Prompts Agêntico (Agentic Prompt Chaining)**, também conhecido como "Prompt Chaining" ou "Sequential Prompting", é uma técnica fundamental na construção de interações mais complexas e sofisticadas com Modelos de Linguagem (LLMs). Em vez de tentar resolver um problema com um único prompt massivo, o problema é decomposto em uma sequência de prompts menores e mais focados, onde a saída de um prompt alimenta a entrada (ou parte do contexto) do próximo.

Este padrão é uma forma de processo sequencial, mas com ênfase na manipulação e transformação da informação através de múltiplas etapas de interação com o LLM (ou diferentes LLMs/agentes).

## Como Funciona o Encadeamento de Prompts?

1.  **Entrada Inicial (Input):** O processo começa com uma entrada ou pergunta inicial.
2.  **Primeiro LLM/Agente (LLM Call 1):** A entrada é processada pelo primeiro LLM ou agente com um prompt específico.
3.  **Saída Intermediária 1:** Este LLM/agente produz uma saída.
4.  **Portão/Decisão (Gate - Opcional):** Pode haver uma etapa de decisão ou validação aqui.
    *   **Passar (Pass):** Se a saída é satisfatória ou cumpre certas condições, ela (ou uma transformação dela) é passada para o próximo LLM/agente.
    *   **Falhar/Sair (Fail/Exit):** Se a saída não é satisfatória, o processo pode terminar ou seguir um caminho alternativo.
5.  **Segundo LLM/Agente (LLM Call 2):** A saída intermediária alimenta o prompt do segundo LLM/agente.
6.  **Saída Intermediária 2:** Este LLM/agente produz outra saída.
7.  **(Repetir):** O processo pode continuar com mais chamadas LLM/agentes e portões, conforme necessário.
8.  **Saída Final (Output):** A saída do último LLM/agente na cadeia é o resultado final do processo.

**Diagrama (do `README.md` do PraisonAI):**
```mermaid
flowchart LR
    In[Entrada Inicial] --> LLM1[LLM/Agente 1 (Prompt 1)]
    LLM1 -- Saída 1 --> Gate{Portão/Decisão}
    Gate -- Passar --> LLM2[LLM/Agente 2 (Prompt 2)]
    LLM2 -- Saída 2 --> LLM3[LLM/Agente 3 (Prompt 3)]
    LLM3 -- Saída Final --> Out[Resultado Final]
    Gate -- Falhar/Alternativa --> Exit[Sair ou Rota Alternativa]

    style In fill:#8B0000,color:#fff
    style LLM1 fill:#189AB4,color:#fff
    style Gate fill:#FFCA28,color:#000 /* Amarelo para decisão */
    style LLM2 fill:#189AB4,color:#fff
    style LLM3 fill:#189AB4,color:#fff
    style Out fill:#8B0000,color:#fff
    style Exit fill:#333,color:#fff
```

## Casos de Uso

*   **Refinamento Progressivo:**
    *   Prompt 1: Gerar um rascunho inicial de um texto.
    *   Prompt 2: Revisar o rascunho para gramática e clareza.
    *   Prompt 3: Adaptar o tom do texto revisado para um público específico.
*   **Extração e Formatação de Dados:**
    *   Prompt 1: Extrair informações chave de um bloco de texto não estruturado.
    *   Prompt 2: Formatar as informações extraídas em JSON.
*   **Tradução e Adaptação:**
    *   Prompt 1: Traduzir um texto para outro idioma.
    *   Prompt 2: Adaptar a tradução para nuances culturais ou um dialeto específico.
*   **Geração de Código em Etapas:**
    *   Prompt 1: Descrever a funcionalidade de alto nível de uma função.
    *   Prompt 2: Gerar o esqueleto da função em Python com base na descrição.
    *   Prompt 3: Adicionar tratamento de erros e documentação à função gerada.
*   **Resumo Multi-etapas:**
    *   Prompt 1: Identificar os pontos principais de um documento longo.
    *   Prompt 2: Gerar um resumo executivo com base nos pontos principais identificados.
*   **Simulação de Conversa com Múltiplas Personas:** Cada "turno" da conversa pode ser um prompt, com o histórico da conversa alimentando o contexto do próximo.

## Implementação no PraisonAI (Conceitual)

O Encadeamento de Prompts é inerentemente suportado pela estrutura de agentes e tarefas sequenciais do PraisonAI.

1.  **Múltiplos Agentes Sequenciais:**
    *   Defina uma série de agentes onde cada um é especializado em uma etapa da cadeia.
    *   O `goal` e `instructions` de cada agente corresponderiam a um prompt específico na cadeia.
    *   Use o [Processo Sequencial](./01_processos_colaboracao_agentes.md#1-processo-sequencial-sequential-process) para que a saída de um agente seja automaticamente passada como contexto para o próximo.

    **Exemplo YAML Conceitual:**
    ```yaml
    framework: praisonai # ou crewai
    process: sequential

    roles:
      extrator_dados:
        role: "Especialista em Extração"
        goal: "Extrair nome, email e empresa de um texto de cartão de visita."
        instructions: "Dado um texto, identifique e extraia o nome da pessoa, seu endereço de e-mail e o nome da empresa. Retorne apenas esses três dados, um por linha."
        # tasks: # Tarefa implícita de extração

      formatador_json:
        role: "Formatador JSON"
        goal: "Converter dados extraídos para o formato JSON."
        instructions: "Você receberá três linhas de texto: nome, email, empresa. Transforme essas informações em um objeto JSON com as chaves 'nome', 'email' e 'empresa'."
        # tasks: # Tarefa implícita de formatação, usando a saída do 'extrator_dados' como contexto

    # A entrada inicial seria dada ao 'extrator_dados'.
    # A saída do 'extrator_dados' seria automaticamente o input para 'formatador_json'.
    ```

2.  **Múltiplas Tarefas para um Único Agente (ou Agentes em um Workflow):**
    *   Defina um agente e atribua a ele uma série de tarefas sequenciais.
    *   A descrição de cada tarefa atuaria como um prompt na cadeia.
    *   Use `context_tasks` para garantir a ordem correta e a passagem de contexto.

    **Exemplo YAML Conceitual com Tarefas Explícitas:**
    ```yaml
    framework: praisonai
    roles:
      escritor_multifacetado:
        role: "Assistente de Escrita Completo"
        goal: "Produzir um artigo de blog bem escrito e otimizado."
        # instructions gerais para o agente

    tasks:
      - name: gerar_rascunho
        agent: escritor_multifacetado
        description: "Escreva um rascunho de 500 palavras sobre os benefícios da meditação para a produtividade."
        expected_output: "Texto do rascunho inicial."

      - name: revisar_gramatica
        agent: escritor_multifacetado
        description: "Revise o texto fornecido (resultado do 'gerar_rascunho') para erros de gramática e ortografia. Forneça o texto corrigido."
        expected_output: "Texto revisado gramaticalmente."
        context_tasks: [gerar_rascunho]

      - name: otimizar_seo
        agent: escritor_multifacetado
        description: "Analise o texto revisado (resultado do 'revisar_gramatica') e sugira 3 palavras-chave de SEO para incorporar. Reescreva o primeiro parágrafo para incluir uma delas."
        expected_output: "Primeiro parágrafo reescrito e lista de 3 palavras-chave."
        context_tasks: [revisar_gramatica]
    ```

3.  **Programaticamente (Python):**
    *   Você pode simplesmente chamar `agente.start()` (ou um método similar) múltiplas vezes, usando a saída de uma chamada como entrada para a próxima.
    *   Bibliotecas como LangChain (que o PraisonAI integra) têm abstrações específicas para cadeias de prompts (ex: `SequentialChain`, `LLMChain`).

    **Exemplo Python Conceitual:**
    ```python
    from praisonaiagents import Agent

    # Supondo que OPENAI_API_KEY está configurada
    agente_prompt1 = Agent(instructions="Traduza o seguinte texto para o francês: {texto_original}")
    agente_prompt2 = Agent(instructions="Explique o significado da seguinte frase em francês em uma sentença simples em português: {frase_frances}")

    texto_ingles = "Hello, how are you today?"

    # Primeira chamada na cadeia
    texto_frances = agente_prompt1.start(texto_original=texto_ingles)
    # (A API do PraisonAI pode variar na forma de passar inputs nomeados para o prompt)
    # Ou, mais diretamente:
    # texto_frances = agente_prompt1.start(f"Traduza o seguinte texto para o francês: {texto_ingles}")


    print(f"Texto em Francês: {texto_frances}")

    # Segunda chamada na cadeia, usando a saída da primeira
    explicacao_portugues = agente_prompt2.start(frase_frances=texto_frances)
    # Ou:
    # explicacao_portugues = agente_prompt2.start(f"Explique o significado da seguinte frase em francês em uma sentença simples em português: {texto_frances}")

    print(f"Explicação em Português: {explicacao_portugues}")
    ```

## Vantagens do Encadeamento de Prompts

*   **Melhora da Qualidade:** Decompor o problema permite que o LLM foque em uma sub-tarefa específica por vez, geralmente levando a resultados melhores do que um único prompt complexo.
*   **Maior Controle:** Permite inspecionar e modificar saídas intermediárias.
*   **Redução de Alucinações:** Prompts mais focados podem reduzir a chance de o LLM gerar informações incorretas.
*   **Facilidade de Debugging:** Se algo der errado, é mais fácil identificar em qual etapa da cadeia o problema ocorreu.
*   **Modularidade:** Cada prompt/agente na cadeia pode ser desenvolvido e testado independentemente.

## "Gates" (Portões/Decisões)

A inclusão de "gates" ou etapas de decisão entre as chamadas de LLM adiciona mais poder ao encadeamento. Um "gate" pode ser:
*   Uma chamada a uma função Python que valida a saída intermediária.
*   Outra chamada LLM que decide se a qualidade é suficiente para prosseguir.
*   Uma solicitação de feedback humano.

Se a saída não passar pelo "gate", o workflow pode terminar, tentar a etapa anterior novamente com um prompt modificado, ou seguir um caminho alternativo.

O Encadeamento de Prompts Agêntico é uma técnica versátil e poderosa, fundamental para construir aplicações LLM robustas e capazes de realizar tarefas complexas em múltiplas etapas.

A seguir, exploraremos o padrão **Avaliador-Otimizador Agêntico (Agentic Evaluator Optimizer)**.
