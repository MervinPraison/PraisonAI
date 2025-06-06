# Exemplo Prático: Análise de Ações com Agentes YAML

Este exemplo prático illustra como você poderia configurar um sistema multi-agente usando PraisonAI e YAML para realizar uma análise básica de uma ação da bolsa de valores.

**Nota:** O arquivo `examples/cookbooks/yaml/stock_analysis_agents.ipynb` no repositório PraisonAI provavelmente contém uma implementação funcional deste caso de uso. Como não podemos processar o conteúdo de notebooks diretamente aqui, vamos construir um exemplo YAML conceitual que demonstre a abordagem. Recomendamos fortemente que você explore o notebook original para ver a implementação real e o código Python que o acompanha.

## Problema a Ser Resolvido

Imagine que você quer automatizar o processo de obter uma visão geral sobre uma determinada ação. Isso poderia envolver:
1.  Coletar notícias recentes sobre a empresa.
2.  Analisar o sentimento geral dessas notícias.
3.  Obter dados financeiros básicos (ex: preço atual, alta/baixa do ano).
4.  Gerar um breve resumo com uma recomendação especulativa (comprar, manter, vender), com todos os devidos avisos de que não se trata de aconselhamento financeiro.

## Agentes Envolvidos (Conceitual)

Para resolver este problema, poderíamos definir os seguintes agentes (roles):

1.  **`pesquisador_noticias_financeiras`**:
    *   **Objetivo:** Encontrar as notícias mais recentes e relevantes sobre uma empresa específica.
    *   **Ferramentas:** Uma ferramenta de busca na web (ex: `tavily_search` ou similar).

2.  **`analista_sentimento_noticias`**:
    *   **Objetivo:** Analisar um conjunto de notícias e determinar o sentimento geral (positivo, negativo, neutro).
    *   **Instruções:** Focado em PNL para análise de sentimento.

3.  **`coletor_dados_mercado`**:
    *   **Objetivo:** Obter dados de mercado atuais para a ação (preço, volume, etc.).
    *   **Ferramentas:** Uma ferramenta que se conecta a uma API de dados financeiros (ex: Alpha Vantage, Yahoo Finance API - pode ser uma ferramenta customizada).

4.  **`analista_chefe_investimentos`**:
    *   **Objetivo:** Consolidar todas as informações (notícias, sentimento, dados de mercado) e produzir um resumo final com uma perspectiva (não um conselho financeiro).
    *   **Instruções:** Enfatizar a natureza especulativa e a necessidade de consultar um profissional.

## Exemplo de Configuração YAML (`analise_acao.yaml` - Conceitual)

```yaml
framework: praisonai # Ou crewai, dependendo da preferência de estrutura
topic: "Análise da Ação XYZ" # Pode ser parametrizado ao rodar o `praisonai` CLI

variables:
  nome_empresa: "Nome da Empresa XYZ"
  ticker_acao: "XYZ"

roles:
  pesquisador_noticias_financeiras:
    role: "Pesquisador de Notícias Financeiras"
    goal: "Coletar as 5 notícias mais recentes e relevantes sobre a {nome_empresa} ({ticker_acao})."
    backstory: "Você é um especialista em encontrar informações financeiras atualizadas na web."
    tools:
      - "tavily_search" # Ou outra ferramenta de busca configurada
    tasks:
      buscar_noticias_recentes:
        description: "Use a ferramenta de busca para encontrar as 5 notícias mais importantes sobre a empresa {nome_empresa} ({ticker_acao}) publicadas na última semana. Forneça o título e um breve resumo de cada notícia."
        expected_output: "Uma lista contendo 5 itens, cada um com 'titulo' e 'resumo_noticia'."

  analista_sentimento_noticias:
    role: "Analista de Sentimento de Notícias"
    goal: "Analisar o sentimento geral expresso nas notícias coletadas sobre a {nome_empresa}."
    backstory: "Você é um LLM treinado para identificar nuances de sentimento em textos financeiros."
    # Este agente não precisa de ferramentas externas, apenas processa o texto.
    tasks:
      analisar_sentimento_coletado:
        description: "Com base na lista de notícias fornecida (títulos e resumos), determine o sentimento geral (Positivo, Negativo ou Neutro) sobre a {nome_empresa}. Justifique brevemente sua análise."
        expected_output: "Uma declaração de sentimento (Positivo, Negativo ou Neutro) e uma justificativa de 1-2 frases."
        context_tasks:
          - buscar_noticias_recentes # Depende da saída do pesquisador

  coletor_dados_mercado:
    role: "Coletor de Dados de Mercado"
    goal: "Obter os dados de mercado mais recentes para a ação {ticker_acao}."
    backstory: "Você se conecta a APIs financeiras para buscar cotações e dados de ações em tempo real."
    tools:
      - "api_dados_financeiros" # Ferramenta customizada ou embutida que busca dados de uma API
    tasks:
      buscar_dados_acao:
        description: "Use a ferramenta 'api_dados_financeiros' para obter o preço atual, a variação diária (%), o volume negociado, a máxima e mínima das últimas 52 semanas para a ação {ticker_acao}."
        expected_output: "Um resumo estruturado contendo: preco_atual, variacao_diaria_percentual, volume, maxima_52s, minima_52s."

  analista_chefe_investimentos:
    role: "Analista Chefe de Investimentos (Simulado)"
    goal: "Consolidar todas as informações coletadas (notícias, sentimento, dados de mercado) e fornecer um breve panorama e uma perspectiva especulativa sobre a ação {ticker_acao}."
    backstory: "Você é um analista experiente que combina diferentes fontes de informação para formar uma visão geral, sempre com uma postura cautelosa e ética."
    # Este agente pode precisar de uma ferramenta de cálculo básica, se for fazer projeções simples.
    tasks:
      compilar_relatorio_acao:
        description: |
          Com base nas seguintes informações:
          1. Resumos das notícias recentes.
          2. Análise de sentimento das notícias.
          3. Dados de mercado atuais da ação {ticker_acao}.
          Elabore um relatório conciso (máximo 300 palavras) que inclua:
          - Um breve resumo das notícias e do sentimento.
          - Destaque dos principais dados de mercado.
          - Uma perspectiva especulativa (ex: 'parece promissor para observação', 'momento de cautela', 'potencial de volatilidade').
          Inclua um AVISO LEGAL claro de que este relatório não constitui aconselhamento financeiro e que decisões de investimento devem ser tomadas com um profissional qualificado.
        expected_output: "Um relatório textual de no máximo 300 palavras contendo o panorama da ação {ticker_acao} e o aviso legal."
        context_tasks:
          - analisar_sentimento_coletado
          - buscar_dados_acao

process: sequential # As tarefas e dependências definem a sequência
# Ou poderia ser hierárquico com o 'analista_chefe_investimentos' como manager.
```

## Como Executar (Teórico)

1.  Salve o conteúdo acima como `analise_acao.yaml`.
2.  Configure as ferramentas necessárias (ex: `tavily_search` e uma `api_dados_financeiros` que pode ser uma ferramenta customizada que você precisaria criar e registrar no PraisonAI se não for embutida).
3.  Execute via CLI:
    ```bash
    praisonai analise_acao.yaml
    ```
    Você também pode passar variáveis via CLI se o PraisonAI suportar overrides para a seção `variables` do YAML, por exemplo:
    ```bash
    praisonai analise_acao.yaml --vars "nome_empresa='Outra Empresa SA';ticker_acao='OTR4'"
    ```
    (A sintaxe exata para override de variáveis dependeria da implementação da CLI do PraisonAI).

## Resultado Esperado (Conceitual)

O `analista_chefe_investimentos` produziria um relatório final, algo como:

> **Panorama da Ação XYZ ({ticker_acao})**
>
> As notícias recentes sobre a Nome da Empresa XYZ indicam um sentimento geralmente [Positivo/Negativo/Neutro], com destaque para [mencionar brevemente um ponto chave das notícias]. Por exemplo, [resumo de uma notícia relevante].
>
> Atualmente, a ação {ticker_acao} está cotada a [preco_atual], com uma variação diária de [variacao_diaria_percentual]% e volume de [volume]. A máxima das últimas 52 semanas foi de [maxima_52s] e a mínima de [minima_52s].
>
> **Perspectiva Especulativa:**
> Com base nas informações atuais, o cenário para {ticker_acao} sugere [perspectiva, ex: 'um potencial interessante para acompanhamento devido ao sentimento positivo das notícias, mas a volatilidade do mercado exige cautela.'].
>
> **AVISO LEGAL:** Este relatório é gerado por um sistema de IA para fins ilustrativos e educacionais, baseado em informações publicamente disponíveis e não constitui aconselhamento financeiro. Qualquer decisão de investimento deve ser tomada após consulta a um profissional financeiro qualificado e análise individual. Não nos responsabilizamos por quaisquer perdas ou ganhos decorrentes do uso desta informação.

## Fundamentos PraisonAI Aplicados

*   **Múltiplos Agentes (`roles`):** Cada agente com sua especialização, `goal`, `backstory` e `tools`.
*   **Tarefas (`tasks`):** Descrições claras do que cada agente deve fazer e o `expected_output`.
*   **Contexto entre Tarefas (`context_tasks`):** A saída de uma tarefa alimenta a próxima, criando um fluxo de trabalho.
*   **Ferramentas (`tools`):** Uso de ferramentas para interagir com o mundo externo (busca na web, APIs financeiras).
*   **Configuração YAML:** Definição declarativa de todo o sistema de agentes.
*   **Processo Sequencial:** As dependências entre tarefas guiam a ordem de execução.

Este exemplo, mesmo conceitual, demonstra o poder do PraisonAI para orquestrar múltiplos agentes na resolução de um problema do mundo real. Ao explorar o notebook `stock_analysis_agents.ipynb` original, você poderá ver como esses conceitos são traduzidos em código e configurações YAML reais.
