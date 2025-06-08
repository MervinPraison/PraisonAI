# TODO: Translate this file to English

# Workflows Avançados: Avaliador-Otimizador Agêntico (Agentic Evaluator Optimizer)

O padrão **Avaliador-Otimizador Agêntico (Agentic Evaluator Optimizer)**, também conhecido como ciclo Gerador-Avaliador ou Crítico-Executor, é um workflow iterativo projetado para refinar e melhorar progressivamente a qualidade de uma solução ou saída gerada por um Modelo de Linguagem (LLM) ou agente.

Este padrão envolve pelo menos dois papéis principais (que podem ser desempenhados por diferentes LLMs/agentes ou pelo mesmo LLM com diferentes prompts):

1.  **Gerador (Generator) / Executor:** Responsável por criar uma solução inicial ou uma tentativa de resposta para um dado problema ou tarefa.
2.  **Avaliador (Evaluator) / Crítico:** Responsável por analisar a solução gerada pelo Gerador, compará-la com critérios de qualidade ou objetivos, e fornecer feedback construtivo.

## Como Funciona o Ciclo Avaliador-Otimizador?

1.  **Entrada (Input) / Problema:** O ciclo começa com um problema a ser resolvido ou uma tarefa a ser realizada.
2.  **Geração (Generator):** O agente Gerador produz uma primeira versão da solução ou resposta.
3.  **Avaliação (Evaluator):** A solução do Gerador é passada para o agente Avaliador. O Avaliador:
    *   Compara a solução com critérios pré-definidos, exemplos de boas respostas, ou o objetivo original.
    *   Identifica pontos fortes, fracos, erros, ou áreas para melhoria.
    *   Gera um feedback detalhado.
4.  **Decisão:** Com base no feedback do Avaliador:
    *   **Aceitar:** Se a solução for considerada boa o suficiente (atinge um certo limiar de qualidade), o ciclo termina e a solução é aceita como saída final.
    *   **Rejeitar + Feedback (Otimizar):** Se a solução precisa de melhorias, o feedback do Avaliador é fornecido de volta ao Gerador.
5.  **Re-Geração / Otimização (Generator):** O Gerador recebe a solução anterior e o feedback do Avaliador. Ele então tenta produzir uma nova versão melhorada da solução, incorporando o feedback.
6.  **Loop:** O processo retorna à etapa de Avaliação (3) com a nova solução. Este ciclo iterativo continua até que a solução seja aceita ou um número máximo de iterações seja atingido.

**Diagrama (do `README.md` do PraisonAI):**
```mermaid
flowchart LR
    In[Entrada/Problema] --> Generator[LLM/Agente Gerador]
    Generator -- SOLUÇÃO v1 --> Evaluator[LLM/Agente Avaliador]
    Evaluator -- ACEITA --> Out[Saída Final Aceita]
    Evaluator -- REJEITADA + FEEDBACK --> Generator

    style In fill:#8B0000,color:#fff
    style Generator fill:#189AB4,color:#fff
    style Evaluator fill:#FFCA28,color:#000 /* Amarelo para avaliação */
    style Out fill:#8B0000,color:#fff
```

## Casos de Uso

*   **Escrita de Textos de Alta Qualidade:**
    *   Gerador: Escreve um rascunho de um artigo.
    *   Avaliador: Verifica clareza, coesão, gramática, tom, e se o artigo cumpre os requisitos. Fornece sugestões de reescrita.
*   **Geração de Código:**
    *   Gerador: Escreve uma função em Python.
    *   Avaliador: Verifica se o código funciona, segue as boas práticas, é eficiente, e tem tratamento de erros. Pode até tentar executar o código e analisar os resultados.
*   **Design de Soluções:**
    *   Gerador: Propõe uma arquitetura para um sistema de software.
    *   Avaliador: Analisa a proposta quanto a escalabilidade, segurança, custo, e manutenibilidade.
*   **Resolução de Problemas Complexos:**
    *   Gerador: Sugere uma estratégia para resolver um problema de lógica.
    *   Avaliador: Verifica a validade da estratégia e aponta falhas no raciocínio.
*   **Otimização de Prompts:** O próprio feedback pode ser usado para refinar o prompt original que o Gerador está usando.
*   **Auto-correção / Auto-reflexão Avançada:** O PraisonAI menciona "Self Reflection AI Agents". O ciclo Avaliador-Otimizador é uma forma poderosa de implementar auto-reflexão, onde o "Avaliador" pode ser o mesmo agente Gerador, mas operando sob um prompt diferente focado na crítica e melhoria.

## Implementação no PraisonAI (Conceitual)

Este padrão geralmente requer um workflow que gerencia o ciclo iterativo:

1.  **Agente Gerador:**
    *   `role`, `goal`, `instructions` focados na criação da solução inicial.
    *   Pode ter ferramentas específicas para sua tarefa de geração.

2.  **Agente Avaliador:**
    *   `role`, `goal`, `instructions` focados na análise crítica da solução do Gerador. Suas instruções devem incluir os critérios de avaliação.
    *   Pode ter ferramentas para ajudar na avaliação (ex: um linter de código, uma ferramenta para verificar fatos).

3.  **Lógica de Orquestração (Pode ser um Agente Gerente ou código Python):**
    *   Gerencia o loop: envia a tarefa inicial para o Gerador, passa a saída para o Avaliador, passa o feedback de volta para o Gerador.
    *   Implementa a condição de parada (solução aceita ou máximo de iterações).

**Exemplo YAML Conceitual (com um Agente Gerente Orquestrando):**
```yaml
framework: praisonai
# process: hierarchical ou custom workflow
# manager_agent: orquestrador_ciclo

roles:
  orquestrador_ciclo:
    role: "Orquestrador do Ciclo de Melhoria"
    goal: "Gerenciar o processo iterativo de geração e avaliação para produzir um código Python de alta qualidade."
    instructions: |
      Seu objetivo é obter uma função Python que some dois números.
      1. Delegue a tarefa de escrever a função inicial para o 'programador_junior'.
      2. Receba a função e delegue a tarefa de avaliá-la para o 'revisor_codigo_senior'.
      3. Se o 'revisor_codigo_senior' aprovar (responder com "APROVADO"), a tarefa está concluída.
      4. Se o 'revisor_codigo_senior' fornecer feedback, passe a função original E o feedback para o 'programador_junior' para uma nova tentativa.
      5. Repita os passos 2-4 no máximo 3 vezes. Se não for aprovado em 3 tentativas, encerre com a última versão e o feedback.
    # tasks: ...

  programador_junior:
    role: "Programador Python Junior"
    goal: "Escrever código Python funcional com base nas especificações e feedback."
    instructions: "Escreva uma função Python chamada 'soma' que recebe dois argumentos e retorna sua soma. Se receber feedback, use-o para corrigir e melhorar a função."
    # tasks: ...

  revisor_codigo_senior:
    role: "Revisor de Código Senior"
    goal: "Avaliar código Python quanto à funcionalidade, clareza e boas práticas, fornecendo feedback construtivo."
    instructions: |
      Você receberá uma função Python. Avalie-a com base nos seguintes critérios:
      - Funcionalidade: Ela soma dois números corretamente?
      - Clareza: O código é fácil de entender?
      - Boas Práticas: Segue as convenções do Python (PEP8)?
      Se a função estiver boa, responda APENAS com a palavra "APROVADO".
      Caso contrário, forneça um feedback específico sobre o que precisa ser melhorado.
    # tools: # Poderia ter uma ferramenta para executar o código
    # tasks: ...
```

**Programaticamente (Python):**
```python
from praisonaiagents import Agent # ou de onde vier Agent

# Configurar os agentes (gerador, avaliador)
gerador = Agent(instructions="Gere um slogan para uma cafeteria.")
avaliador = Agent(instructions="Avalie o slogan: '{slogan_gerado}'. É curto, memorável e atraente? Se não, sugira melhorias. Se sim, diga 'Perfeito'.")

slogan_atual = None
feedback = None
max_iteracoes = 3

for i in range(max_iteracoes):
    prompt_gerador = "Gere um slogan para uma cafeteria."
    if feedback: # Se houver feedback, adiciona ao prompt do gerador
        prompt_gerador += f" Considere o seguinte feedback para melhoria: {feedback}"

    slogan_atual = gerador.start(prompt_gerador)
    print(f"Iteração {i+1} - Slogan Gerado: {slogan_atual}")

    feedback_avaliador = avaliador.start(slogan_gerado=slogan_atual) # Passando o slogan para o prompt do avaliador
    print(f"Iteração {i+1} - Feedback do Avaliador: {feedback_avaliador}")

    if "Perfeito" in feedback_avaliador: # Condição de parada
        print("Slogan final aceito!")
        break

    feedback = feedback_avaliador # Prepara o feedback para a próxima iteração
else:
    print("Máximo de iterações atingido. Usando o último slogan gerado.")

# Resultado final é 'slogan_atual'
```

## Vantagens do Padrão

*   **Melhoria da Qualidade:** A natureza iterativa e o feedback explícito geralmente levam a resultados de maior qualidade do que uma única tentativa.
*   **Resolução de Problemas Complexos:** Permite abordar problemas que são difíceis de resolver corretamente na primeira tentativa.
*   **Simula Processos Humanos:** Espelha como os humanos frequentemente trabalham: criar, obter feedback, refinar.
*   **Customização da Avaliação:** Os critérios de avaliação podem ser altamente personalizados para a tarefa em questão.

## Desafios

*   **Custo e Latência:** Cada iteração envolve pelo menos duas chamadas LLM (uma para o Gerador, uma para o Avaliador), o que pode aumentar o custo e o tempo de execução.
*   **Qualidade do Feedback:** A eficácia do ciclo depende muito da qualidade do feedback do Avaliador. Um feedback vago ou ruim não ajudará o Gerador.
*   **Convergência:** Não há garantia de que o processo sempre convergirá para uma solução perfeita. É importante ter critérios de parada (ex: número máximo de iterações, tempo limite).
*   **Definição dos Critérios de Avaliação:** Criar prompts ou lógica para o Avaliador que reflitam com precisão os critérios de qualidade desejados pode ser desafiador.

O padrão Avaliador-Otimizador Agêntico é uma técnica poderosa para alcançar resultados de alta qualidade e para tarefas que se beneficiam de um processo de refinamento iterativo. O PraisonAI, com sua capacidade de orquestrar múltiplos agentes e workflows, está bem posicionado para implementar este padrão.

A seguir, veremos os **Agentes Repetitivos (Repetitive Agents)**.
