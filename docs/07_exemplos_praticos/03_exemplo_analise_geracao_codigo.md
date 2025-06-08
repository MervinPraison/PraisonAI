# TODO: Translate this file to English

# Exemplo Prático: Análise e Geração Simples de Código com Agentes YAML

Este exemplo prático demonstra como o PraisonAI pode ser configurado para auxiliar em tarefas relacionadas a código, como explicar um trecho de código existente ou gerar um script simples com base em uma descrição.

**Nota:** Os exemplos `examples/cookbooks/Code_Analysis_Agent.ipynb` e `examples/cookbooks/yaml/cli_operation_agents.ipynb` no repositório PraisonAI podem conter implementações funcionais e mais detalhadas. Este é um exemplo conceitual para ilustrar a abordagem com YAML.

## Problema a Ser Resolvido

Queremos um sistema de agentes que possa:
1.  **Explicar um trecho de código:** Dado um código em uma linguagem específica, o agente deve explicar sua funcionalidade, lógica e possíveis usos.
2.  **Gerar um script simples:** Dada uma descrição de uma tarefa (ex: "criar um script Python que lista arquivos em um diretório"), o agente deve gerar o código correspondente.

## Agentes Envolvidos (Conceitual)

1.  **`analista_codigo_fonte`**:
    *   **Objetivo:** Analisar e explicar trechos de código em várias linguagens.
    *   **Instruções:** Focado em PNL para "entender" código e descrevê-lo em linguagem natural.
    *   **Ferramentas:** Poderia opcionalmente usar uma ferramenta de "code interpreter" para testar o código, mas para explicação, o LLM pode ser suficiente.

2.  **`gerador_scripts_python`**:
    *   **Objetivo:** Gerar scripts Python funcionais com base em descrições de tarefas.
    *   **Instruções:** Focado em traduzir requisitos em linguagem natural para código Python.
    *   **Ferramentas:** Opcionalmente, um "code interpreter" para testar o script gerado.

## Exemplo de Configuração YAML (`codigo_agentes.yaml` - Conceitual)

```yaml
framework: praisonai
topic: "Análise e Geração de Código Python"

variables:
  linguagem_padrao: "Python"
  diretorio_alvo_exemplo: "./minha_pasta"

roles:
  analista_codigo_fonte:
    role: "Engenheiro de Software Explicador"
    goal: "Analisar e fornecer explicações claras e concisas sobre trechos de código na {linguagem_padrao} ou outra linguagem especificada."
    backstory: "Você é um desenvolvedor sênior com vasta experiência em múltiplas linguagens e uma habilidade especial para explicar código complexo de forma simples."
    # tools:
    #   - "code_interpreter" # Opcional, para testes
    tasks:
      explicar_trecho_codigo:
        # Este é um exemplo de tarefa que seria chamada com um input específico.
        # O input (o código a ser explicado) viria da execução do 'praisonai' CLI
        # ou de outro agente que passa o contexto.
        description: "Analise o seguinte trecho de código em {linguagem_padrao} e explique:
1. Qual o seu propósito principal?
2. Como ele funciona (lógica passo a passo)?
3. Em que tipo de situação ele seria útil?

Código a ser analisado:
```python
{codigo_para_analisar}
```"
        expected_output: "Uma explicação textual clara, dividida em propósito, funcionamento e utilidade do código fornecido."
        # 'codigo_para_analisar' seria uma variável de input da tarefa.

  gerador_scripts_python:
    role: "Desenvolvedor Python Automatizado"
    goal: "Gerar scripts Python funcionais e bem documentados com base em descrições de requisitos."
    backstory: "Você é um especialista em Python capaz de traduzir rapidamente especificações em scripts eficientes."
    # tools:
    #   - "code_interpreter" # Para testar o script gerado
    #   - "file_write_tool"  # Para salvar o script em um arquivo
    tasks:
      gerar_script_listar_arquivos:
        # Exemplo de tarefa específica.
        description: "Crie um script Python que lista todos os arquivos e subdiretórios dentro de um diretório especificado ('{diretorio_alvo_exemplo}' por padrão, mas pode ser sobrescrito). O script deve imprimir os nomes no console."
        expected_output: "O código completo do script Python solicitado, pronto para ser executado."
        # Poderia ter uma tarefa subsequente para salvar e testar o script.

      gerar_script_customizado:
        # Tarefa mais genérica que espera uma descrição do script.
        description: "Com base na seguinte solicitação, gere um script Python: '{descricao_script_customizado}'"
        expected_output: "O código completo do script Python solicitado."
        # 'descricao_script_customizado' seria uma variável de input.

# Você poderia definir um processo sequencial ou hierárquico se as tarefas
# de análise e geração fossem encadeadas ou gerenciadas.
# Para este exemplo, cada agente pode ser invocado para sua tarefa específica.
```

## Como Executar (Teórico)

A execução dependeria de como você passa os inputs específicos (como `codigo_para_analisar` ou `descricao_script_customizado`) para as tarefas.

**Opção 1: Foco em uma Tarefa Específica ao Invocar**

Se a CLI do PraisonAI permitir invocar uma tarefa específica de um agente e passar contexto/variáveis para ela (isso é comum em sistemas como Airflow, mas pode variar no PraisonAI):

```bash
# Para explicar um código (hipotético, depende da capacidade da CLI)
# Supondo que você possa passar 'codigo_para_analisar' como uma variável de tarefa
praisonai codigo_agentes.yaml --task explicar_trecho_codigo --vars "codigo_para_analisar='def hello(n):
  print(f"Hello {n}")'"

# Para gerar o script padrão de listar arquivos
praisonai codigo_agentes.yaml --task gerar_script_listar_arquivos

# Para gerar um script customizado
praisonai codigo_agentes.yaml --task gerar_script_customizado --vars "descricao_script_customizado='Um script que lê um arquivo de texto e conta o número de palavras.'"
```

**Opção 2: Modificar o YAML para cada Execução**

Você poderia ter um placeholder no YAML e substituí-lo antes de cada execução, ou ter diferentes arquivos YAML para diferentes códigos/scripts.

**Opção 3: Agente "Interface com Usuário"**

Um agente inicial poderia pegar a entrada do usuário (o código a ser analisado ou a descrição do script) e então passar essa informação como contexto para o `analista_codigo_fonte` ou `gerador_scripts_python`.

## Resultado Esperado (Conceitual)

*   **Para `explicar_trecho_codigo`**: O agente `analista_codigo_fonte` retornaria um texto explicando o código fornecido.
    > Exemplo: "O código fornecido define uma função Python chamada `hello` que recebe um argumento `n`. Seu propósito é imprimir uma saudação personalizada no console, incluindo o valor de `n`. Ele funciona usando uma f-string para formatar a mensagem. Seria útil em situações onde você precisa de uma saudação simples ou para demonstrar a passagem de argumentos para funções."

*   **Para `gerar_script_listar_arquivos`**: O agente `gerador_scripts_python` retornaria um bloco de código Python.
    ```python
    # Resultado esperado (conceitual):
    import os

    def listar_arquivos_e_diretorios(caminho_diretorio="."):
        """
        Lista todos os arquivos e subdiretórios dentro do caminho_diretorio especificado.
        """
        try:
            print(f"Conteúdo do diretório: {os.path.abspath(caminho_diretorio)}")
            for item in os.listdir(caminho_diretorio):
                print(item)
        except FileNotFoundError:
            print(f"Erro: Diretório não encontrado - {caminho_diretorio}")
        except Exception as e:
            print(f"Ocorreu um erro: {e}")

    if __name__ == "__main__":
        # Por padrão, lista o diretório alvo do YAML, mas pode ser alterado.
        diretorio_alvo = "{diretorio_alvo_exemplo}" # Esta variável seria substituída
        # ou o script poderia aceitar um argumento de linha de comando.
        # listar_arquivos_e_diretorios(diretorio_alvo)
        # Para um exemplo funcional direto:
        listar_arquivos_e_diretorios() # Lista o diretório atual
    ```

## Fundamentos PraisonAI Aplicados

*   **Especialização de Agentes:** Agentes distintos para análise e para geração de código.
*   **Instruções Claras (`goal`, `instructions`, `description` da tarefa):** Essenciais para que os LLMs entendam a tarefa relacionada a código.
*   **Parametrização (`variables`, inputs de tarefa):** Permite reutilizar os agentes para diferentes códigos ou descrições de script.
*   **Potencial Uso de Ferramentas:** Embora não detalhado aqui, ferramentas como `code_interpreter` (para executar e testar código) ou `file_write_tool` (para salvar scripts) seriam adições valiosas para tornar os agentes mais autônomos e úteis. O PraisonAI menciona "Code Interpreter Agents" como um recurso.

Este exemplo mostra como agentes podem ser aplicados a domínios técnicos como programação. A qualidade da explicação ou do código gerado dependerá muito da capacidade do LLM subjacente e da clareza dos prompts e instruções fornecidas aos agentes.
