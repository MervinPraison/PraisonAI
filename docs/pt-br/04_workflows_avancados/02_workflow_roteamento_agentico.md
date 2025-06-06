# Workflows Avançados: Roteamento Agêntico (Agentic Routing)

O **Roteamento Agêntico (Agentic Routing Workflow)** é um padrão de workflow avançado onde as tarefas ou consultas são dinamicamente direcionadas para diferentes Modelos de Linguagem (LLMs) ou agentes especializados, com base no conteúdo ou na natureza da entrada.

Este padrão é particularmente útil quando você tem acesso a múltiplos LLMs, cada um com suas próprias forças (ex: um LLM ótimo para escrita criativa, outro para análise de código, um terceiro mais rápido e barato para tarefas simples), ou quando diferentes agentes são especializados em domínios distintos.

## Como Funciona o Roteamento Agêntico?

O fluxo geral é:

1.  **Entrada (Input):** Uma nova tarefa, pergunta ou dado de entrada é recebido pelo sistema.
2.  **Roteador (Router):** Um componente central, que pode ser ele mesmo um LLM ou um agente com lógica específica, analisa a entrada.
3.  **Decisão de Roteamento:** Com base na análise, o Roteador decide qual LLM ou agente especializado é o mais adequado para processar a entrada.
4.  **Delegação:** A entrada é enviada para o LLM ou agente selecionado.
5.  **Processamento:** O LLM/agente selecionado processa a entrada e produz um resultado.
6.  **Saída (Output):** O resultado é retornado.

**Diagrama (do `README.md` do PraisonAI):**
\`\`\`mermaid
flowchart LR
    In[Entrada] --> Router[Roteador de Chamadas LLM]
    Router -- Rota A --> LLM1[LLM/Agente A (Ex: Criativo)]
    Router -- Rota B --> LLM2[LLM/Agente B (Ex: Código)]
    Router -- Rota C --> LLM3[LLM/Agente C (Ex: Rápido/Simples)]
    LLM1 -- Resultado A --> Out[Saída]
    LLM2 -- Resultado B --> Out
    LLM3 -- Resultado C --> Out

    style In fill:#8B0000,color:#fff
    style Router fill:#2E8B57,color:#fff
    style LLM1 fill:#189AB4,color:#fff
    style LLM2 fill:#189AB4,color:#fff
    style LLM3 fill:#189AB4,color:#fff
    style Out fill:#8B0000,color:#fff
\`\`\`

## Casos de Uso

*   **Otimização de Custos e Performance:** Usar LLMs menores e mais rápidos para tarefas simples e LLMs maiores e mais poderosos (e caros) apenas quando necessário.
*   **Especialização de Tarefas:** Direcionar consultas sobre programação para um LLM treinado em código, perguntas sobre história para um LLM com vasto conhecimento histórico, etc.
*   **Seleção de Agentes Especializados:** Em um sistema com múltiplos agentes PraisonAI, cada um com um `role` e `tools` diferentes, um roteador pode enviar a tarefa para o agente mais qualificado.
*   **Tratamento de Linguagem:** Direcionar entradas em diferentes idiomas para LLMs com melhor performance naquele idioma específico.
*   **Balanceamento de Carga:** Distribuir requisições entre vários LLMs idênticos para evitar sobrecarga.

## Implementação no PraisonAI (Conceitual)

A implementação de um Roteador Agêntico no PraisonAI pode ser feita de algumas maneiras:

1.  **Agente Roteador Dedicado (Manager Agent):**
    *   Você pode definir um agente PraisonAI específico para atuar como o roteador.
    *   **Instruções do Agente Roteador:** As instruções para este agente seriam algo como: "Dada uma tarefa, decida qual dos seguintes especialistas (Agente A, Agente B, Agente C) é o mais adequado para resolvê-la. Responda apenas com o nome do especialista."
    *   **Ferramentas:** Este agente não precisaria de ferramentas externas, apenas da capacidade de escolher entre opções.
    *   **Lógica de Workflow:** Um processo hierárquico ou um workflow customizado seria construído onde o Agente Roteador recebe a tarefa primeiro, e seu output (o nome do especialista) é usado para direcionar a tarefa para o próximo agente no fluxo.

    **Exemplo YAML Conceitual:**
    \`\`\`yaml
    framework: praisonai
    # process: hierarchical # ou um workflow customizado
    # manager_agent: roteador_principal

    roles:
      roteador_principal:
        role: "Coordenador de Tarefas Inteligente"
        goal: "Analisar cada tarefa e designá-la ao especialista mais apropriado."
        instructions: |
          Você receberá uma tarefa. Sua função é decidir qual dos seguintes especialistas deve lidar com ela:
          - 'escritor_criativo': Para tarefas que envolvem escrita de histórias, poemas, roteiros.
          - 'programador_python': Para tarefas relacionadas a código Python, algoritmos ou scripts.
          - 'assistente_geral': Para perguntas factuais simples ou tarefas gerais.
          Responda APENAS com o identificador do especialista (ex: 'escritor_criativo').
        # tasks: # O roteador teria uma tarefa implícita de roteamento

      escritor_criativo:
        role: "Escritor Criativo"
        goal: "Gerar textos criativos e artísticos."
        # ... tasks para escrita ...

      programador_python:
        role: "Especialista em Python"
        goal: "Resolver problemas de programação e gerar código Python."
        # ... tasks para programação ...

      assistente_geral:
        role: "Assistente Geral"
        goal: "Responder a perguntas gerais e realizar tarefas simples."
        # ... tasks gerais ...

    # A lógica do workflow (não mostrada aqui) usaria o output do 'roteador_principal'
    # para enviar a tarefa original para o 'role' escolhido.
    \`\`\`

2.  **Uso de "Router Chains" (se integrado com LangChain):**
    *   Se o PraisonAI estiver usando LangChain por baixo dos panos, você pode aproveitar as "Router Chains" do LangChain. Essas cadeias são projetadas especificamente para analisar a entrada e direcioná-la para outra cadeia ou LLM.
    *   Isso envolveria definir as diferentes "rotas" (LLMs ou cadeias de destino) e os prompts que ajudam o LLM roteador a tomar a decisão.

3.  **Lógica Condicional em Workflows Customizados:**
    *   Em um workflow definido programaticamente (Python), você pode usar um LLM para classificar a intenção da entrada e, em seguida, usar estruturas `if/else` ou `switch` para enviar a tarefa para o agente ou LLM apropriado.

## Considerações ao Implementar Roteamento Agêntico

*   **Qualidade do Roteamento:** A eficácia do sistema depende da capacidade do Roteador de tomar decisões precisas. Um roteamento ruim pode levar a resultados subótimos ou custos mais altos.
*   **Overhead:** A etapa de roteamento adiciona uma chamada LLM (se o roteador for um LLM) ou lógica computacional, o que introduz alguma latência e custo. Isso precisa ser balanceado com os ganhos de usar o LLM/agente especializado correto.
*   **Complexidade:** Configurar e manter um sistema de roteamento pode adicionar complexidade ao seu design de agentes.
*   **Clareza das Descrições das Rotas:** Se o roteador é um LLM, ele precisa de descrições claras de cada rota/especialista para tomar boas decisões (semelhante a como os agentes usam descrições de ferramentas).

O Roteamento Agêntico é uma técnica poderosa para construir sistemas de IA mais eficientes, especializados e econômicos. Ao permitir que seu sistema escolha dinamicamente a melhor "ferramenta" (neste caso, o melhor LLM ou agente) para o trabalho, você pode alcançar resultados significativamente melhores.

A seguir, exploraremos o padrão **Agentic Orchestrator Worker**.
