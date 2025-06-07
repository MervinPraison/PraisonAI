# Módulo: Ferramentas (Tools) no PraisonAI

As **Ferramentas (Tools)** são um componente essencial que transforma os [Agentes](./../02_conceitos_fundamentais/01_agentes.md) do PraisonAI de meros processadores de linguagem em entidades capazes de interagir com o mundo real, executar ações e acessar informações externas. O PraisonAI destaca o suporte a "Mais de 100 Ferramentas Personalizadas", além da capacidade de criar as suas próprias.

Este módulo explora como as ferramentas funcionam no PraisonAI, como utilizá-las e como desenvolvê-las. Já introduzimos o conceito básico de ferramentas em [Conceitos Fundamentais - Ferramentas](./../02_conceitos_fundamentais/04_ferramentas.md), aqui vamos aprofundar.

## A Importância das Ferramentas e Suas Descrições

Para um Modelo de Linguagem Grande (LLM) utilizar uma ferramenta eficazmente, ele precisa entender:
1.  **O que a ferramenta faz:** Qual seu propósito?
2.  **Quando usá-la:** Em que situações ou para quais tipos de perguntas/tarefas ela é relevante?
3.  **Quais argumentos ela espera:** Que informações de entrada a ferramenta necessita?
4.  **O que ela retorna:** Qual o formato e o tipo de saída da ferramenta?

Essa compreensão é quase inteiramente derivada da **descrição da ferramenta** (geralmente a docstring da função em Python) e do **esquema dos seus argumentos** (tipos e nomes dos parâmetros).

> [!CRITICAL] Descrições Claras São Cruciais!
> A qualidade da descrição da sua ferramenta impacta diretamente a capacidade do LLM de usá-la corretamente. Descrições vagas ou imprecisas levarão a um uso incorreto ou à não utilização da ferramenta.

## Usando Ferramentas Embutidas no PraisonAI

PraisonAI oferece um vasto conjunto de ferramentas prontas para uso. Embora uma lista exaustiva esteja além do escopo deste guia (consulte a documentação oficial do PraisonAI ou explore o código-fonte para detalhes específicos), o uso delas geralmente segue um padrão:

*   **Identificação da Ferramenta:** Você precisa saber o nome ou identificador da ferramenta que deseja usar (ex: `tavily_search`, `web_scraper`, `code_interpreter`, `file_read_tool`).
*   **Atribuição ao Agente:**
    *   **Em YAML:** Na definição de um `role` (agente), você pode listar as ferramentas que ele tem permissão para usar na seção `tools`:
        \`\`\`yaml
        roles:
          pesquisador_avancado:
            role: "Pesquisador Avançado"
            goal: "Encontrar e analisar informações detalhadas sobre tópicos complexos."
            tools:
              - "tavily_search"       # Ferramenta de busca na web (exemplo)
              - "web_page_reader"   # Ferramenta para ler conteúdo de URLs
              # - "nome_outra_ferramenta_embutida"
            # ... outras configurações ...
        \`\`\`
    *   **Em Python:** Ao instanciar um `Agent`, você passa uma lista de objetos de ferramenta ou nomes de ferramentas registradas para o parâmetro `tools`.
        \`\`\`python
        from praisonaiagents import Agent
        # Supondo que as ferramentas embutidas possam ser importadas ou referenciadas por nome
        # from praisonai.tools import TavilySearchTool, WebScraperTool # Exemplo conceitual

        # ferramentas_disponiveis = [TavilySearchTool(), WebScraperTool()]
        # OU, se referenciadas por nome:
        # ferramentas_disponiveis = ["tavily_search", "web_scraper"]

        # agente = Agent(
        #     role="Pesquisador",
        #     goal="Coletar informações da web.",
        #     tools=ferramentas_disponiveis
        # )
        \`\`\`
        A forma exata de instanciar/referenciar ferramentas embutidas em Python dependerá de como elas são expostas pela biblioteca `praisonaiagents`. Verifique os exemplos no repositório.

*   **Invocação pelo LLM:** Uma vez que um agente tem uma ferramenta atribuída, o LLM do agente decidirá autonomamente quando usá-la durante a execução de uma tarefa, com base nas instruções da tarefa e na descrição da ferramenta.

## Criando Ferramentas Personalizadas

A verdadeira flexibilidade do PraisonAI (e de frameworks como LangChain, que ele integra) reside na facilidade de criar ferramentas personalizadas para atender às necessidades específicas do seu projeto.

O método mais comum em Python é definir uma função e decorá-la para transformá-la em uma ferramenta que o LLM possa entender.

**Exemplo Chave: `examples/python/general/example_custom_tools.py`**

Este arquivo no repositório PraisonAI é uma excelente referência. Ele demonstra o uso do decorator `@tool` (frequentemente vindo de `langchain_core.tools` ou uma utilidade similar fornecida pelo PraisonAI).

\`\`\`python
# Adaptado de examples/python/general/example_custom_tools.py
from langchain_core.tools import tool # Ou um decorator similar do PraisonAI
from pydantic import BaseModel, Field # Para definir o esquema dos argumentos

# Exemplo 1: Ferramenta Simples
@tool
def get_word_length(word: str) -> int:
    """Retorna o comprimento de uma palavra."""
    return len(word)

# Exemplo 2: Ferramenta com descrição mais elaborada e esquema de entrada Pydantic
class CalculatorInput(BaseModel):
    a: int = Field(description="Primeiro número")
    b: int = Field(description="Segundo número")

@tool("calculator_tool", args_schema=CalculatorInput) # Nome explícito e esquema
def calculator(a: int, b: int) -> int:
    """Calcula a soma de dois números, 'a' e 'b'."""
    return a + b

# Como usar essas ferramentas com um agente PraisonAI:
# from praisonaiagents import Agent
#
# meu_agente = Agent(
#     role="Assistente Inteligente",
#     goal="Resolver tarefas usando ferramentas personalizadas.",
#     tools=[get_word_length, calculator] # Adiciona as funções decoradas à lista de ferramentas
# )
#
# resultado_comprimento = meu_agente.start("Qual o comprimento da palavra 'PraisonAI'?")
# print(f"Resultado (comprimento): {resultado_comprimento}")
#
# resultado_soma = meu_agente.start("Some 15 e 27 usando a calculadora.")
# print(f"Resultado (soma): {resultado_soma}")
\`\`\`

**Pontos Cruciais na Criação de Ferramentas Personalizadas:**

1.  **Decorator `@tool`:**
    *   Este decorator (ou um similar como `@structured_tool` ou utilitários do PraisonAI) é o que registra a função como uma ferramenta utilizável pelo sistema de agentes.
    *   Ele pode aceitar argumentos, como um nome explícito para a ferramenta ou um `args_schema` para definir a estrutura dos argumentos de entrada de forma mais robusta (usando Pydantic).

2.  **Docstring (Descrição da Ferramenta):**
    *   **ESSENCIAL!** A docstring da sua função (a string entre aspas triplas \`\`\`"..." \`\`\` logo após a definição da função) é usada pelo LLM para entender o que a ferramenta faz.
    *   Seja claro, conciso e preciso. Explique o propósito, os parâmetros esperados (mesmo que tipados, a descrição ajuda) e o que a ferramenta retorna.

3.  **Type Hints (Anotações de Tipo):**
    *   Use anotações de tipo do Python (ex: `word: str`, `-> int`). Elas ajudam o LLM (e o Pydantic, se usado) a entender os tipos de dados esperados e retornados, o que é crucial para o "function calling".

4.  **Schema de Argumentos (Pydantic - Opcional, mas Recomendado para Complexidade):**
    *   Para ferramentas com múltiplos argumentos ou argumentos com descrições específicas, usar um modelo Pydantic (`BaseModel`) para definir o `args_schema` é uma excelente prática. Isso fornece uma estrutura clara e validável para os inputs da ferramenta.

## O Mecanismo de "Function Calling" / "Tool Using"

Quando um LLM (como os modelos mais recentes da OpenAI, Gemini, etc.) é informado sobre as ferramentas disponíveis (seus nomes, descrições e esquemas de argumentos), ele pode, durante uma conversa ou ao processar uma tarefa, decidir que precisa de uma ferramenta. Se isso acontecer, o LLM não executa a ferramenta diretamente. Em vez disso, ele:

1.  **Gera uma Solicitação de Chamada de Ferramenta:** O LLM produz uma saída estruturada (geralmente JSON) indicando o nome da ferramenta que ele quer chamar e os valores dos argumentos que ele inferiu do contexto da conversa/tarefa.
2.  **Execução pelo Framework:** O framework (PraisonAI, LangChain) intercepta essa solicitação.
3.  Ele então chama a função Python real correspondente à ferramenta, passando os argumentos fornecidos pelo LLM.
4.  **Resultado da Ferramenta:** A função Python executa sua lógica e retorna um resultado.
5.  **Retorno ao LLM:** O framework envia este resultado de volta para o LLM.
6.  **Resposta Final:** O LLM agora usa o resultado da ferramenta (junto com o histórico da conversa e o prompt original) para formular sua resposta final ao usuário ou para decidir a próxima ação.

Este ciclo permite que os LLMs "usem" ferramentas de forma segura e estruturada, sem realmente executar código arbitrário por si mesmos.

## Ferramentas e o PraisonAI

O PraisonAI facilita esse processo, seja usando suas ferramentas embutidas ou permitindo a integração suave de ferramentas personalizadas. Ao definir agentes, você simplesmente os equipa com as ferramentas necessárias, e o PraisonAI, em conjunto com o LLM, gerencia a lógica de quando e como essas ferramentas são chamadas.

A capacidade de estender agentes com ferramentas customizadas é o que permite adaptar o PraisonAI a praticamente qualquer domínio ou caso de uso específico, tornando-o uma plataforma verdadeiramente versátil para a construção de aplicações de IA.
