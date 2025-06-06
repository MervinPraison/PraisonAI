# O que é o PraisonAI?

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../recursos/logo_dark.png" />
    <source media="(prefers-color-scheme: light)" srcset="../recursos/logo_light.png" />
    <img alt="PraisonAI Logo" src="../recursos/logo_light.png" />
  </picture>
</p>

PraisonAI é um framework de **Múltiplos Agentes de IA (Multi-AI Agents)** pronto para produção e com capacidade de **auto-reflexão**. Ele foi projetado para criar Agentes de IA que automatizam e resolvem problemas, desde tarefas simples até desafios complexos. Ao integrar PraisonAI Agents, AG2 (anteriormente AutoGen) e CrewAI em uma solução de **baixo código (low-code)**, ele simplifica a construção e o gerenciamento de sistemas LLM multi-agentes, enfatizando a simplicidade, personalização e colaboração eficaz entre humanos e agentes.

<div align="center">
  <a href="https://docs.praison.ai" target="_blank" rel="noopener noreferrer">
    <p align="center">
      <img src="https://img.shields.io/badge/_Documentação_Oficial_(Inglês)-Visite_docs.praison.ai-blue?style=for-the-badge&logo=bookstack&logoColor=white" alt="Documentação Oficial" />
    </p>
  </a>
</div>

## Principais Recursos (Key Features)

O PraisonAI oferece uma vasta gama de funcionalidades para construir agentes poderosos:

- **Criação Automatizada de Agentes de IA:** Facilidade na definição e instanciação de agentes.
- **Agentes de IA com Auto-Reflexão:** Capacidade dos agentes de analisar e melhorar seu próprio desempenho.
- **Agentes de IA com Raciocínio:** Habilidade de realizar pensamentos lógicos e dedutivos.
- **Agentes de IA Multi Modais:** Suporte para processar diferentes tipos de dados (texto, imagem, etc.).
- **Colaboração Multi-Agente:** Permite que múltiplos agentes trabalhem juntos em tarefas complexas.
- **Workflow de Agentes de IA:** Definição de fluxos de trabalho para orquestrar a interação entre agentes.
- **Adição de Conhecimento Personalizado (RAG):** Integre bases de conhecimento específicas para seus agentes.
- **Agentes com Memória de Curto e Longo Prazo:** Capacidade de reter informações entre interações.
- **Agentes para Conversar com PDF:** Extraia informações e interaja com o conteúdo de arquivos PDF.
- **Agentes Interpretadores de Código:** Permitem que agentes executem código para realizar tarefas.
- **Processamento Assíncrono e Paralelo:** Execução eficiente de tarefas.
- **Auto Agents:** Agentes que podem gerar outros agentes ou modificar a si mesmos.
- **Agentes Matemáticos:** Especializados em resolver problemas matemáticos.
- **Agentes com Saída Estruturada:** Garantem que a resposta do agente siga um formato específico.
- **Agentes Integrados com LangChain:** Aproveite o ecossistema LangChain.
- **Agentes com Callback:** Funções que são chamadas em determinados pontos da execução do agente.
- **Mini Agentes de IA:** Agentes leves para tarefas específicas.
- **Mais de 100 Ferramentas Personalizadas:** Um vasto conjunto de ferramentas prontas para uso.
- **Configuração via YAML:** Defina agentes e workflows de forma declarativa.
- **Suporte a Mais de 100 Modelos de LLM:** Flexibilidade na escolha do modelo de linguagem.

## Fluxo dos Agentes de IA (AI Agents Flow)

Este diagrama ilustra um fluxo básico de como os agentes podem interagir em um sistema:

\`\`\`mermaid
graph LR
    Inicio(Inicio) --> Agente1
    Agente1 --> Processo(Processar)
    Processo --> Agente2
    Agente2 --> Resultado(Resultado)
    Processo -.-> Agente1
    subgraph Agente1["Agente 1"]
        Tarefa1(Tarefa)
        IconeAgente1("Agente de IA")
        Ferramentas1(Ferramentas)
        Tarefa1 --- IconeAgente1
        IconeAgente1 --- Ferramentas1
    end
    subgraph Agente2["Agente 2"]
        Tarefa2(Tarefa)
        IconeAgente2("Agente de IA")
        Ferramentas2(Ferramentas)
        Tarefa2 --- IconeAgente2
        IconeAgente2 --- Ferramentas2
    end
    classDef input fill:#8B0000,stroke:#7C90A0,color:#fff
    classDef process fill:#189AB4,stroke:#7C90A0,color:#fff
    classDef tools fill:#2E8B57,stroke:#7C90A0,color:#fff
    classDef transparent fill:none,stroke:none
    class Inicio,Resultado,Tarefa1,Tarefa2 input
    class Processo,IconeAgente1,IconeAgente2 process
    class Ferramentas1,Ferramentas2 tools
    class Agente1,Agente2 transparent
\`\`\`
* **Explicação:** O processo geralmente começa com uma entrada (Início) que é passada para um Agente 1. Este agente, utilizando suas Ferramentas, processa sua Tarefa. O resultado pode ser passado para um Agente 2 para processamento adicional ou pode haver um ciclo onde o processo retorna ao Agente 1. Finalmente, um Resultado é produzido.

## Agentes de IA com Ferramentas (AI Agents with Tools)

Os agentes no PraisonAI podem utilizar ferramentas para interagir com sistemas externos e realizar ações:

\`\`\`mermaid
flowchart TB
    subgraph Ferramentas
        direction TB
        T3["Busca na Internet"]
        T1["Execucao de Codigo"]
        T2["Formatacao"]
    end
    Entrada["Entrada"] ---> Agentes
    subgraph Agentes
        direction LR
        A1["Agente 1"]
        A2["Agente 2"]
        A3["Agente 3"]
    end
    Agentes ---> Saida["Saida"]
    T3 --> A1
    T1 --> A2
    T2 --> A3
    style Ferramentas fill:#189AB4,color:#fff
    style Agentes fill:#8B0000,color:#fff
    style Entrada fill:#8B0000,color:#fff
    style Saida fill:#8B0000,color:#fff
\`\`\`
* **Explicação:** Diferentes agentes (Agente 1, Agente 2, Agente 3) podem ser equipados com diversas ferramentas (Busca na Internet, Execução de Código, Formatação). Com base na Entrada, os agentes utilizam suas ferramentas para processar a informação e gerar uma Saída.

## Agentes de IA com Memória (AI Agents with Memory)

A capacidade de memória permite que os agentes mantenham contexto e informação através de múltiplas tarefas:

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
* **Explicação:** Os agentes podem acessar memória de Curto Prazo (para contexto imediato) e de Longo Prazo (para conhecimento persistente). A memória de Longo Prazo é frequentemente implementada utilizando um Banco de Dados Vetorial (Vector DB) para buscas semânticas eficientes. Os agentes interagem com essa memória para informar suas ações e gerar a Saída.

> [!NOTE] Nota sobre os Logos
> Os logos originais do PraisonAI (light/dark) não estão presentes neste repositório. Se desejar usá-los, você precisará baixá-los do repositório original ou da documentação oficial e colocá-los na pasta \`docs/pt-br/recursos/\`. As referências de imagem neste arquivo foram ajustadas para \`../recursos/logo_light.png\` e \`../recursos/logo_dark.png\`.

Este arquivo serve como uma introdução geral ao PraisonAI. Nos próximos tópicos, detalharemos cada um desses recursos e conceitos.
