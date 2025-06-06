# Exemplo Prático: Geração de Artigos com Agentes YAML

Este exemplo demonstra como o PraisonAI pode ser usado para automatizar o processo de criação de um artigo, desde a pesquisa inicial e esboço até a redação final e revisão. Utilizaremos uma abordagem baseada em YAML para definir os agentes e suas tarefas.

**Nota:** O arquivo `examples/cookbooks/yaml/article_generation_agents.ipynb` no repositório PraisonAI provavelmente contém uma implementação funcional deste caso de uso. Este exemplo é uma representação conceitual. Explore o notebook original para a implementação detalhada.

## Problema a Ser Resolvido

Criar um artigo informativo e bem estruturado sobre um tópico específico. O processo envolve:
1.  Pesquisar informações relevantes sobre o tópico.
2.  Criar um esboço (outline) para o artigo.
3.  Escrever o conteúdo do artigo com base no esboço e na pesquisa.
4.  Revisar o artigo para clareza, gramática e estilo.

## Agentes Envolvidos (Conceitual)

1.  **`pesquisador_topicos`**:
    *   **Objetivo:** Coletar informações e fatos chave sobre o tópico do artigo.
    *   **Ferramentas:** Ferramenta de busca na web.

2.  **`arquiteto_conteudo`**:
    *   **Objetivo:** Criar um esboço detalhado e lógico para o artigo, com base na pesquisa.
    *   **Instruções:** Focado em estruturação de conteúdo.

3.  **`redator_artigos`**:
    *   **Objetivo:** Escrever o conteúdo completo do artigo, seguindo o esboço e utilizando as informações pesquisadas.
    *   **Instruções:** Focado em escrita fluida e engajante.

4.  **`revisor_critico`**:
    *   **Objetivo:** Revisar o artigo escrito, verificando erros, melhorando a clareza e garantindo que o objetivo foi atingido.
    *   **Instruções:** Focado em análise crítica e sugestões de melhoria.

## Exemplo de Configuração YAML (`geracao_artigo.yaml` - Conceitual)

```yaml
framework: praisonai # Ou crewai
topic: "O Impacto da Inteligência Artificial na Educação Superior"

variables:
  titulo_artigo_alvo: "IA na Educação Superior: Uma Revolução no Aprendizado"
  publico_alvo: "Educadores, administradores acadêmicos e estudantes universitários"
  numero_palavras_alvo: 1200

roles:
  pesquisador_topicos:
    role: "Pesquisador Especialista"
    goal: "Coletar informações abrangentes e atuais sobre '{topic}'."
    backstory: "Você é um pesquisador meticuloso, capaz de encontrar dados relevantes, estudos de caso e opiniões de especialistas."
    tools:
      - "tavily_search"
    tasks:
      pesquisar_informacoes_artigo:
        description: "Realize uma pesquisa completa sobre '{topic}'. Colete dados sobre aplicações atuais, benefícios, desafios, e o futuro da IA neste contexto. Priorize fontes acadêmicas e reportagens de tecnologia confiáveis dos últimos 2 anos."
        expected_output: "Um documento compilado com os principais pontos de informação, links para fontes, e citações relevantes, organizado por subtemas."

  arquiteto_conteudo:
    role: "Arquiteto de Conteúdo"
    goal: "Criar um esboço (outline) lógico e detalhado para um artigo sobre '{topic}' com o título '{titulo_artigo_alvo}'."
    backstory: "Você é especialista em estruturar informações complexas de forma clara e sequencial para artigos e relatórios."
    tasks:
      criar_esboco_artigo:
        description: "Com base no material de pesquisa fornecido sobre '{topic}', crie um esboço detalhado para um artigo intitulado '{titulo_artigo_alvo}'. O esboço deve incluir: Introdução (com gancho e tese), seções principais (com 3-5 pontos chave cada), subseções se necessário, e Conclusão (com resumo e chamada para ação ou reflexão). O artigo deve ser direcionado para {publico_alvo} e ter aproximadamente {numero_palavras_alvo} palavras."
        expected_output: "Um esboço hierárquico completo do artigo, formatado em markdown, pronto para ser usado pelo redator."
        context_tasks:
          - pesquisar_informacoes_artigo

  redator_artigos:
    role: "Redator de Artigos Experiente"
    goal: "Escrever um artigo envolvente e informativo sobre '{topic}', seguindo o esboço e usando a pesquisa fornecida."
    backstory: "Você transforma esboços e dados de pesquisa em artigos bem escritos, com linguagem clara e adaptada ao público-alvo."
    tasks:
      escrever_conteudo_artigo:
        description: "Utilizando o esboço detalhado e o material de pesquisa sobre '{topic}', escreva o conteúdo completo do artigo '{titulo_artigo_alvo}'. Siga a estrutura do esboço, desenvolva cada ponto com as informações pesquisadas, e mantenha um tom apropriado para {publico_alvo}. O artigo deve ter aproximadamente {numero_palavras_alvo} palavras."
        expected_output: "O texto completo do artigo, formatado em markdown."
        context_tasks:
          - criar_esboco_artigo # Depende do esboço
          # Implicitamente também depende de 'pesquisar_informacoes_artigo' via 'criar_esboco_artigo'

  revisor_critico:
    role: "Revisor e Editor Crítico"
    goal: "Revisar o artigo '{titulo_artigo_alvo}' para garantir alta qualidade, clareza, precisão e coesão, sugerindo melhorias."
    backstory: "Você tem um olhar apurado para detalhes, gramática, estilo e lógica argumentativa. Seu objetivo é elevar a qualidade do texto."
    tasks:
      revisar_artigo_final:
        description: |
          Revise o artigo fornecido sobre '{topic}' com o título '{titulo_artigo_alvo}'.
          Verifique os seguintes aspectos:
          1. Clareza e fluidez do texto.
          2. Correção gramatical e ortográfica.
          3. Coesão e coerência entre as seções.
          4. Se o artigo atinge o objetivo proposto no esboço e se é adequado para o {publico_alvo}.
          5. Se a contagem de palavras está próxima de {numero_palavras_alvo}.
          Forneça feedback construtivo detalhado E, se possível, o texto com as correções diretas ou sugestões de reescrita incorporadas.
        expected_output: "Um relatório de revisão com feedback detalhado e/ou o texto do artigo com as revisões sugeridas/aplicadas."
        context_tasks:
          - escrever_conteudo_artigo

process: sequential
# As dependências (context_tasks) garantem a ordem correta das operações.
```

## Como Executar (Teórico)

1.  Salve o conteúdo como `geracao_artigo.yaml`.
2.  Certifique-se de que a ferramenta `tavily_search` (ou a que você escolheu) está configurada.
3.  Execute via CLI:
    ```bash
    praisonai geracao_artigo.yaml
    ```
    Você pode alterar o `topic` e outras `variables` diretamente no arquivo YAML ou investigar se a sua versão do PraisonAI CLI permite a substituição de variáveis via linha de comando.

## Resultado Esperado (Conceitual)

O `revisor_critico` (ou o `redator_artigos` se o revisor apenas fornecer feedback para uma nova iteração do redator) produziria o texto final do artigo, revisado e pronto para publicação, ou um relatório de revisão.

Por exemplo, a saída da tarefa `escrever_conteudo_artigo` seria o rascunho do artigo. A saída da tarefa `revisar_artigo_final` seria o artigo já com as melhorias ou com comentários para o redator aplicar.

## Fundamentos PraisonAI Aplicados

*   **Divisão de Trabalho:** Múltiplos agentes, cada um focado em uma etapa do processo de criação do artigo.
*   **Workflow Sequencial:** O processo segue uma lógica clara: pesquisa -> esboço -> redação -> revisão.
*   **Passagem de Contexto:** A informação gerada por um agente (pesquisa, esboço) é usada como entrada essencial para o próximo.
*   **Instruções Detalhadas (`description` e `expected_output`):** Guiam cada agente a produzir o resultado necessário para a etapa seguinte.
*   **Variáveis:** Permitem parametrizar o processo para diferentes tópicos ou requisitos de artigo.

Este exemplo illustra como um processo criativo, como a escrita de um artigo, pode ser decomposto e automatizado com a colaboração de múltiplos agentes especializados no PraisonAI. A qualidade do resultado final dependerá significativamente da clareza dos `goals`, `instructions` e `expected_output` de cada agente e tarefa.
