# Usando o PraisonAI com YAML (No-Code / Low-Code)

Uma das grandes vantagens do PraisonAI é sua capacidade de definir e orquestrar agentes de IA usando arquivos de configuração YAML. Essa abordagem "No-Code" ou "Low-Code" permite que usuários, mesmo sem profundo conhecimento de programação, construam sistemas de agentes complexos de forma declarativa.

## A Interface de Linha de Comando (CLI) `praisonai`

Para trabalhar com arquivos YAML, você usará principalmente a interface de linha de comando `praisonai`. Certifique-se de tê-la instalada (geralmente via `pip install praisonai` - veja o [Guia de Instalação](./../01_instalacao/00_instalacao_windows.md)).

**Comandos Principais:**

*   `praisonai <arquivo.yaml>`: Executa a configuração de agentes definida no `<arquivo.yaml>`.
*   `praisonai --auto "sua tarefa aqui"`: Modo de geração automática onde o PraisonAI tenta criar e executar agentes para a tarefa descrita.
*   `praisonai --init "descrição da tarefa"`: Ajuda a inicializar um arquivo `agents.yaml` básico com base na descrição fornecida.
*   `praisonai --version`: Mostra a versão instalada.
*   `praisonai --help`: Exibe informações de ajuda e outras opções da CLI.

## Estrutura Básica de um Arquivo YAML (`agents.yaml`)

Um arquivo YAML para PraisonAI (comumente chamado `agents.yaml`, mas pode ter qualquer nome) define os componentes do seu sistema de agentes. Vamos analisar a estrutura com base nos exemplos do PraisonAI.

**Exemplo Simples (adaptado do `README.md` principal):**

```yaml
# framework: Define qual framework de agentes o PraisonAI deve utilizar por baixo dos panos.
# Pode ser 'praisonai' (nativo), 'crewai', ou 'autogen'.
framework: praisonai

# topic: Uma variável global que pode ser usada dentro de outras strings no YAML
# usando a sintaxe {topic}. Útil para parametrizar seus agentes.
topic: "Inteligência Artificial e o Futuro do Trabalho"

# roles: Define os diferentes agentes (ou papéis) no seu sistema.
roles:
  # 'pesquisador' é um nome/identificador para este agente/papel.
  pesquisador:
    role: "Pesquisador Especialista em IA" # O nome formal do papel.
    goal: "Conduzir pesquisas aprofundadas sobre o impacto da {topic}."
    backstory: "Você é um analista de tendências tecnológicas com um olhar crítico e habilidade para encontrar informações relevantes e dados prospectivos sobre {topic}."
    # instructions: (Opcional aqui, pode ser mais geral ou focado em tarefas específicas)
    # llm: (Opcional) Especifica o modelo LLM para este agente.
    #   model: "gpt-3.5-turbo"
    #   temperature: 0.7
    # tools: (Opcional) Lista de ferramentas que este agente pode usar.
    #   - 'tavily_search' # Exemplo de ferramenta de busca
    # memory: (Opcional) Configurações de memória para o agente.
    #   enabled: true
    tasks:
      # 'tarefa_coleta_dados' é um nome/identificador para esta tarefa.
      tarefa_coleta_dados:
        description: "Coletar artigos, estudos e opiniões de especialistas publicados nos últimos 6 meses sobre o impacto da {topic}. Identificar os principais argumentos, previsões e preocupações."
        expected_output: "Um relatório compilado contendo um resumo dos principais achados, lista de fontes e trechos relevantes. O relatório deve ter no máximo 1000 palavras."
        # agent: pesquisador # Opcional se a tarefa está aninhada sob o 'role' que a executa.
        # async_execution: false # Se a tarefa pode ser executada de forma assíncrona.

  # Você pode definir múltiplos 'roles' (agentes)
  escritor:
    role: "Escritor de Conteúdo Estratégico"
    goal: "Produzir um artigo de blog envolvente e informativo baseado na pesquisa sobre {topic}."
    backstory: "Você é um escritor talentoso, capaz de traduzir informações complexas em conteúdo acessível e cativante para um público geral interessado em tecnologia."
    tasks:
      tarefa_redacao_artigo:
        description: "Com base no relatório de pesquisa fornecido sobre {topic}, escrever um artigo de blog de aproximadamente 800 palavras. O artigo deve ser bem estruturado, com introdução, desenvolvimento dos pontos principais e conclusão. Usar uma linguagem clara e exemplos práticos."
        expected_output: "O texto final do artigo de blog, pronto para publicação, incluindo um título chamativo e sugestões de subtítulos."
        context_tasks: # Define que esta tarefa depende do resultado de outra(s).
          - tarefa_coleta_dados # O resultado da 'tarefa_coleta_dados' do 'pesquisador' será passado como contexto.

# tasks: (Opcional) Você também pode definir uma lista global de tarefas
# e atribuí-las aos agentes, especialmente útil para workflows mais complexos
# ou quando um agente gerente distribui tarefas.
# tasks:
#   - name: tarefa_global_de_revisao
#     agent: revisor # Supondo um agente 'revisor' definido em 'roles'
#     description: "Revisar o artigo de blog final quanto à clareza, gramática e precisão."
#     expected_output: "Artigo revisado com sugestões de melhoria."
#     context_tasks:
#       - tarefa_redacao_artigo

# process: (Opcional) Define o tipo de processo de colaboração.
# Ex: sequential, hierarchical. Se não especificado, um padrão é usado (geralmente sequencial).
# process: sequential

# manager_agent: (Opcional) Se estiver usando um processo hierárquico,
# especifica qual 'role' atua como o gerente.
# manager_agent: pesquisador # Exemplo
```

**Principais Seções do YAML:**

*   `framework` (Obrigatório): Especifica qual backend de agentes usar (`praisonai`, `crewai`, `autogen`). Isso influencia como o YAML é interpretado e quais funcionalidades estão disponíveis.
*   `topic` (Opcional): Uma variável global para reutilizar texto.
*   `roles` (Obrigatório): Define cada agente.
    *   `role` (str): O nome do papel do agente.
    *   `goal` (str): O objetivo principal do agente.
    *   `backstory` (str): Contexto para o LLM.
    *   `instructions` (str, Opcional): Instruções gerais para o agente.
    *   `llm` (dict, Opcional): Configurações do LLM (modelo, temperatura, etc.).
    *   `tools` (list, Opcional): Ferramentas que o agente pode usar.
    *   `memory` (dict, Opcional): Configurações de memória.
    *   `tasks` (dict, Opcional, aninhado sob um `role`): Tarefas específicas para este agente.
        *   `description` (str): O que a tarefa envolve.
        *   `expected_output` (str): O resultado esperado.
        *   `agent` (str, Opcional): Qual agente executa (útil se as tarefas são listadas globalmente).
        *   `context_tasks` (list, Opcional): Lista de nomes de tarefas das quais esta tarefa depende. O resultado dessas tarefas será passado como contexto.
        *   `async_execution` (bool, Opcional): Se a tarefa pode ser executada de forma assíncrona.
*   `tasks` (list, Opcional, nível raiz): Uma lista global de tarefas. Útil para workflows onde um agente gerente distribui trabalho ou para definir uma sequência explícita. Cada item da lista é um dicionário com as mesmas chaves de uma tarefa aninhada (`name`, `description`, `expected_output`, `agent`, `context_tasks`, etc.).
*   `process` (str, Opcional): Tipo de processo de colaboração (ex: `sequential`, `hierarchical`).
*   `manager_agent` (str, Opcional): Nome do `role` que atua como gerente em processos hierárquicos.

## Executando o Arquivo YAML

1.  Salve sua configuração em um arquivo (ex: `meus_agentes.yaml`).
2.  Abra seu terminal.
3.  Execute:
    ```bash
    praisonai meus_agentes.yaml
    ```
4.  O PraisonAI irá:
    *   Ler e validar o arquivo YAML.
    *   Instanciar os agentes e tarefas definidos.
    *   Orquestrar a execução das tarefas pelos agentes, conforme o processo e as dependências especificadas.
    *   Imprimir os resultados e logs no console (o nível de detalhe pode depender de configurações `verbose` ou globais).

## Modo Automático (`--auto`)

Para tarefas mais simples ou para obter um ponto de partida rápido, você pode usar o modo `--auto`:

```bash
praisonai --auto "Crie um resumo do livro 'O Pequeno Príncipe' em 3 parágrafos."
```
O PraisonAI tentará interpretar a solicitação, possivelmente criar agentes e tarefas internamente, e executar o processo para gerar o resultado.

## Inicializando um YAML (`--init`)

Se você não tem certeza de como começar seu arquivo YAML, o PraisonAI pode ajudar:

```bash
praisonai --init "Planejar uma campanha de marketing para um novo aplicativo de fitness"
```
Isso geralmente cria um arquivo `agents.yaml` básico com uma estrutura inicial baseada na sua descrição, que você pode então refinar.

## Vantagens da Abordagem YAML

*   **Acessibilidade:** Permite que não-programadores ou programadores com menos experiência em Python construam sistemas de IA.
*   **Clareza e Legibilidade:** A estrutura declarativa do YAML pode tornar a configuração do sistema de agentes fácil de entender.
*   **Configuração Rápida:** Ideal para prototipagem rápida e experimentação.
*   **Reutilização:** Arquivos YAML podem servir como templates para diferentes projetos.

## Explorando Exemplos YAML

A pasta `examples/cookbooks/yaml/` no repositório PraisonAI é o melhor lugar para encontrar exemplos práticos e avançados de configurações YAML. Lá você encontrará diversos arquivos `.ipynb` (Jupyter Notebooks) que carregam e executam arquivos YAML para casos de uso como:

*   Geração de artigos
*   Resposta automática de e-mails
*   Escrita de livros
*   Lançamento de produtos
*   E muito mais!

Analise esses exemplos para entender como estruturar seus próprios arquivos YAML para diferentes tipos de problemas e workflows.

A seguir, veremos como interagir com o PraisonAI usando JavaScript e TypeScript.
