# Conceito Fundamental: Conhecimento (Knowledge) e RAG

Além da [Memória](./05_memoria.md) para conversas e interações, os [Agentes](./01_agentes.md) do PraisonAI frequentemente precisam acessar e utilizar um corpo de **Conhecimento (Knowledge)** específico para realizar suas [Tarefas](./02_tarefas.md) de forma eficaz. Uma técnica poderosa para isso é a **Retrieval Augmented Generation (RAG)**.

## O que é Conhecimento no Contexto de Agentes de IA?

Conhecimento, neste contexto, refere-se a um conjunto de informações, dados ou documentos que um agente pode consultar para:

*   Responder a perguntas factuais.
*   Obter contexto específico sobre um domínio.
*   Basear suas respostas e ações em informações atualizadas ou proprietárias.

Os Modelos de Linguagem Grande (LLMs) são pré-treinados em vastas quantidades de texto da internet, mas esse conhecimento:

1.  **Não é atualizado em tempo real:** O conhecimento do LLM "congela" na data em que foi treinado.
2.  **Não inclui dados privados ou proprietários:** LLMs públicos não conhecem os documentos internos da sua empresa, por exemplo.
3.  **Pode "alucinar":** Às vezes, os LLMs podem gerar informações que parecem plausíveis, mas são factualmente incorretas.

Fornecer aos agentes acesso a uma base de conhecimento externa ajuda a mitigar esses problemas.

## RAG (Retrieval Augmented Generation)

**RAG** é uma arquitetura que combina as capacidades de geração de texto dos LLMs com um sistema de recuperação de informação. Em vez de depender apenas do conhecimento interno do LLM, o processo RAG funciona da seguinte forma:

1.  **Pergunta/Consulta do Usuário:** O usuário faz uma pergunta ou atribui uma tarefa ao agente.
2.  **Recuperação (Retrieval):**
    *   A consulta do usuário é usada para buscar informações relevantes em uma base de conhecimento externa (ex: um conjunto de documentos, uma base de dados, artigos da Wikipedia).
    *   Essa busca é frequentemente realizada usando **embeddings e bancos de dados vetoriais**. A consulta e os documentos na base de conhecimento são convertidos em vetores, e o sistema busca os documentos cujos vetores são mais "próximos" (semanticamente similares) ao vetor da consulta.
3.  **Aumento (Augmentation):**
    *   Os trechos de informação mais relevantes recuperados da base de conhecimento são combinados com o prompt original do usuário.
4.  **Geração (Generation):**
    *   O prompt aumentado (contendo a pergunta original + os dados recuperados) é então enviado ao LLM.
    *   O LLM utiliza tanto seu conhecimento interno quanto as informações contextuais fornecidas para gerar uma resposta mais precisa, relevante e baseada nos fatos recuperados.

**Benefícios do RAG:**

*   **Respostas Mais Precisas e Factuais:** Reduz as alucinações, pois as respostas são ancoradas em dados recuperados.
*   **Acesso a Conhecimento Atualizado:** A base de conhecimento pode ser atualizada independentemente do LLM.
*   **Uso de Dados Proprietários:** Permite que os agentes utilizem informações específicas de um domínio ou organização.
*   **Transparência:** É possível (e muitas vezes implementado) citar as fontes de onde a informação foi recuperada, aumentando a confiança na resposta do agente.

## Conhecimento e RAG no PraisonAI

PraisonAI destaca "Adicionar Conhecimento Personalizado" e "RAG Agents" como recursos importantes, indicando suporte robusto para essa arquitetura.

### Como o PraisonAI Implementa Conhecimento e RAG

A implementação geralmente envolve:

1.  **Preparação da Base de Conhecimento:**
    *   **Coleta de Documentos:** Reunir os documentos relevantes (PDFs, TXTs, páginas web, etc.).
    *   **Chunking (Fragmentação):** Dividir documentos longos em pedaços menores (chunks) para processamento e recuperação mais eficientes.
    *   **Embedding e Indexação:** Gerar embeddings para cada chunk e armazená-los em um banco de dados vetorial (Vector DB) para busca rápida. PraisonAI pode integrar-se com várias soluções de Vector DB.

2.  **Configuração do Agente RAG:**
    *   O agente é configurado para usar um processo RAG. Isso significa que, ao receber uma consulta, ele primeiro acionará o mecanismo de recuperação antes de chamar o LLM.
    *   Pode envolver a especificação do Vector DB a ser usado, como as consultas devem ser transformadas em embeddings, e como os resultados recuperados devem ser formatados no prompt para o LLM.

### Exemplos e Uso

*   **Programaticamente (Python):**
    Você provavelmente configuraria um `Retriever` (componente responsável pela busca no Vector DB) e o associaria a um agente ou a uma cadeia (chain) que implementa o fluxo RAG.
    \`\`\`python
    # Exemplo conceitual usando componentes comuns em RAG
    from praisonaiagents import Agent
    # from langchain.vectorstores import Chroma # Exemplo de Vector DB
    # from langchain.embeddings import OpenAIEmbeddings # Exemplo de modelo de embedding
    # from langchain.text_splitter import RecursiveCharacterTextSplitter
    # from langchain.chains import RetrievalQA

    # 1. Carregar e preparar documentos (splitting, embedding, storing in Vector DB)
    # ... (código para popular seu Vector DB com seus documentos) ...
    # vector_store = Chroma(persist_directory="./chroma_db", embedding_function=OpenAIEmbeddings())
    # retriever = vector_store.as_retriever()

    # 2. Criar um agente ou cadeia RAG
    # agente_rag = Agent(
    #     role="Especialista em Documentos",
    #     goal="Responder perguntas com base nos documentos fornecidos.",
    #     # ...
    #     # A forma de integrar o retriever pode variar:
    #     # Pode ser uma ferramenta, um tipo de memória, ou uma configuração específica do agente.
    #     tools=[meu_retriever_tool], # Onde meu_retriever_tool usa o 'retriever'
    #     # ou
    #     # retrieval_config={'retriever': retriever, 'type': 'rag'},
    # )

    # Ou usando uma cadeia como RetrievalQA do LangChain, que o PraisonAI pode integrar
    # qa_chain = RetrievalQA.from_chain_type(llm=meu_llm, chain_type="stuff", retriever=retriever)
    # resultado = qa_chain.run("Qual é o principal tópico do documento X?")
    \`\`\`
    > Veja exemplos como `examples/python/concepts/rag-agents.py` e `examples/python/concepts/knowledge-agents.py` no repositório PraisonAI para implementações concretas.

*   **Declarativamente (YAML):**
    Arquivos YAML podem permitir a especificação de fontes de conhecimento, configurações de Vector DBs ou a ativação de um modo RAG para certos agentes.
    \`\`\`yaml
    # Exemplo conceitual em YAML
    roles:
      especialista_documentos:
        role: Especialista em Documentos
        goal: Responder perguntas com base em nossa base de conhecimento interna.
        knowledge_base:
          type: chroma_db # Ou outro tipo de Vector DB
          path: "./minha_base_de_conhecimento_vectorial"
          embedding_model: "text-embedding-ada-002" # Modelo para gerar embeddings
        # ...
    tasks:
      responder_pergunta_documento:
        description: "Com base no documento 'manual_produto_v2.pdf', qual é o procedimento para resetar o dispositivo?"
        expected_output: "Uma explicação clara do procedimento de reset, citando a página se possível."
        # O agente usaria sua knowledge_base configurada para responder.
    \`\`\`

### "Chat with PDF Agents"

Este é um caso de uso específico do RAG. O agente é configurado para usar um ou mais arquivos PDF como sua base de conhecimento. O PraisonAI simplifica a criação desses agentes, provavelmente lidando com o parsing do PDF, chunking, embedding e o fluxo RAG nos bastidores.

## Fundamentos por Trás

*   **Recuperação de Informação (Information Retrieval):** A ciência de buscar informações em grandes coleções de dados.
*   **Processamento de Linguagem Natural (PLN):** Técnicas para processar e entender texto, incluindo a geração de embeddings.
*   **Bancos de Dados Vetoriais:** Sistemas otimizados para armazenar e pesquisar vetores de alta dimensionalidade.
*   **Arquiteturas de LLM:** Compreender como os LLMs processam prompts e como o contexto adicional (dos documentos recuperados) influencia a geração.

A capacidade de integrar conhecimento externo através de RAG torna os agentes PraisonAI significativamente mais poderosos, permitindo que eles operem com informações específicas do domínio, atualizadas e verificáveis.

Isso conclui nossa exploração dos conceitos fundamentais! A seguir, veremos como usar o PraisonAI na prática.
