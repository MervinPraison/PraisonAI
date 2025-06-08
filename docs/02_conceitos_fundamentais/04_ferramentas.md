# TODO: Translate this file to English

# Conceito Fundamental: Ferramentas (Tools)

Os [Agentes](./01_agentes.md) no PraisonAI, para serem verdadeiramente úteis e interagirem com o mundo além de apenas processar texto, precisam de **Ferramentas (Tools)**. As ferramentas expandem as capacidades dos agentes, permitindo-lhes realizar ações, buscar informações externas e interagir com outros sistemas.

## O que são Ferramentas?

No contexto de agentes de IA e LLMs, uma Ferramenta é essencialmente uma **função ou capacidade específica que um agente pode invocar para realizar uma tarefa que vai além das capacidades inerentes do modelo de linguagem**.

Pense nas ferramentas como os "braços e pernas" do agente, ou como aplicativos especializados que ele pode usar:

*   **Exemplos Comuns:**
    *   **Busca na Web:** Para encontrar informações atualizadas na internet.
    *   **Execução de Código:** Para realizar cálculos, manipular dados ou interagir com sistemas via scripts.
    *   **Leitura/Escrita de Arquivos:** Para acessar ou persistir informações no sistema de arquivos.
    *   **Interação com APIs:** Para se conectar a serviços externos (ex: previsão do tempo, bancos de dados, redes sociais).
    *   **Cálculo Matemático:** Para resolver problemas matemáticos complexos.
    *   **Geração de Imagens:** Para criar imagens a partir de descrições textuais.

O LLM dentro do agente decide *quando* usar uma ferramenta, *qual* ferramenta usar e com *quais parâmetros* chamá-la, com base na tarefa atual e em suas instruções.

## Ferramentas no PraisonAI

PraisonAI possui um rico ecossistema de ferramentas, mencionando "100+ Custom Tools" em sua documentação. Ele permite tanto o uso de ferramentas pré-construídas quanto a criação de ferramentas personalizadas.

### Como o PraisonAI Implementa Ferramentas

1.  **Definição da Ferramenta:**
    Uma ferramenta é tipicamente definida como uma função (em Python, por exemplo) que realiza uma ação específica. Crucialmente, a ferramenta deve ter uma **descrição clara** de seu propósito, argumentos e o que ela retorna. Essa descrição é usada pelo LLM para entender como e quando usar a ferramenta.

2.  **Atribuição ao Agente:**
    As ferramentas são disponibilizadas para um agente. O agente, ao processar uma tarefa, pode então "decidir" usar uma de suas ferramentas disponíveis se julgar necessário.

3.  **Invocação pelo Agente (LLM):**
    Quando o LLM do agente determina que uma ferramenta é necessária, ele geralmente formata uma "chamada de função" (function call) especificando o nome da ferramenta e os argumentos. O framework (PraisonAI) intercepta essa chamada, executa a função da ferramenta correspondente com os argumentos fornecidos, e retorna o resultado da ferramenta para o LLM. O LLM então usa esse resultado para continuar seu processo de pensamento e gerar a resposta final ou a próxima ação.

### Usando Ferramentas Embutidas

PraisonAI facilita o uso de muitas ferramentas comuns. A forma exata de habilitá-las pode variar:

*   **Automaticamente Disponíveis:** Algumas ferramentas básicas podem estar disponíveis por padrão para certos tipos de agentes.
*   **Especificadas na Configuração YAML:**
    ```yaml
    # Exemplo conceitual em YAML
    roles:
      pesquisador_web:
        role: Pesquisador Web
        goal: Encontrar informações relevantes na internet.
        tools:
          - 'tavily_search' # Nome de uma ferramenta de busca na web
          - 'web_scraper'   # Nome de uma ferramenta para extrair conteúdo de páginas
        # ... outras configurações do agente ...
    ```
*   **Adicionadas Programaticamente (Python):**
    ```python
    from praisonaiagents import Agent
    # Supondo a existência de ferramentas definidas em algum lugar
    # from praisonai.tools import minha_ferramenta_busca, minha_ferramenta_calculo

    # Exemplo conceitual
    agente_com_ferramentas = Agent(
        role="Assistente Versátil",
        goal="Resolver problemas usando informações da web e cálculos.",
        # A forma de passar ferramentas pode variar; pode ser uma lista de funções,
        # instâncias de classes de ferramentas, ou nomes de ferramentas registradas.
        tools=[minha_ferramenta_busca, minha_ferramenta_calculo]
    )
    ```
    > Consulte os exemplos em `examples/python/tools/` e `examples/python/general/example_custom_tools.py` para a sintaxe correta de como definir e atribuir ferramentas. O PraisonAI também se integra com ferramentas do LangChain, o que expande enormemente as opções.

### Criando Ferramentas Personalizadas

Uma das grandes vantagens do PraisonAI é a facilidade de criar suas próprias ferramentas.

*   **Em Python:**
    Geralmente, você define uma função Python e a decora com um decorator específico (fornecido pelo PraisonAI ou pela biblioteca de ferramentas que ele usa, como LangChain) para expô-la como uma ferramenta. A descrição da função (docstring) é crucial, pois é o que o LLM usará para entender a ferramenta.

    *Exemplo (inspirado em `examples/python/general/example_custom_tools.py` e LangChain):*
    ```python
    from langchain_core.tools import tool # Exemplo usando decorator do LangChain

    @tool
    def minha_ferramenta_personalizada(texto: str, numero: int) -> str:
        """
        Esta ferramenta recebe um texto e um número.
        Ela concatena o texto com o número e retorna a string resultante.
        Use esta ferramenta quando precisar combinar uma string com um valor numérico.
        """
        return f"{texto} - {numero}"

    # Depois, esta 'minha_ferramenta_personalizada' pode ser adicionada à lista de ferramentas de um agente.
    # agente = Agent(tools=[minha_ferramenta_personalizada, ...])
    ```
    > A descrição dentro das aspas triplas (docstring) é fundamental! Ela deve explicar claramente o que a ferramenta faz, quais argumentos ela espera e o que ela retorna. O LLM usa essa informação para decidir se e como usar a ferramenta.

### O Papel do LLM na Utilização de Ferramentas (Function Calling / Tool Using)

Modelos de LLM modernos (como os da OpenAI, Gemini, etc.) foram treinados com a capacidade de "function calling" ou "tool using". Isso significa que, dada uma lista de ferramentas disponíveis (com suas descrições e esquemas de argumentos), o LLM pode:

1.  Entender a pergunta do usuário ou a tarefa atual.
2.  Determinar se alguma das ferramentas disponíveis pode ajudar a responder à pergunta ou realizar a tarefa.
3.  Se sim, gerar uma estrutura de dados (geralmente JSON) que especifica qual ferramenta chamar e com quais argumentos.
4.  Receber o resultado da execução da ferramenta e usar essa informação para formular a resposta final.

O PraisonAI gerencia esse fluxo de interação entre o LLM e as ferramentas.

## Fundamentos por Trás

*   **Planejamento Automatizado:** A capacidade de um agente de decompor um problema e identificar que precisa de uma capacidade externa (ferramenta) para uma sub-etapa.
*   **Integração de Sistemas:** Ferramentas são a ponte entre o mundo abstrato do LLM e sistemas ou fontes de dados concretos.
*   **Extensibilidade:** Permitem que o comportamento dos agentes seja estendido dinamicamente sem retreinar o LLM.

Dominar o uso e a criação de ferramentas é essencial para construir agentes PraisonAI verdadeiramente poderosos e capazes de resolver problemas do mundo real.

Em seguida, veremos como a **Memória** permite que os agentes mantenham o contexto e aprendam com interações passadas.
