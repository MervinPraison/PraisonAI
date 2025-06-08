# TODO: Translate this file to English

# Guia de Instalação Local (Windows)

Este guia detalha como instalar o framework PraisonAI em um ambiente Windows, permitindo que você comece a criar e executar seus próprios agentes de IA.

## Pré-requisitos

Antes de começar, garanta que você tenha os seguintes pré-requisitos instalados e configurados em seu sistema Windows:

1.  **Python:**
    *   **Versão:** É recomendável usar Python 3.8 ou superior.
    *   **Como verificar:** Abra o Prompt de Comando (CMD) ou PowerShell e digite:
        ```bash
        python --version
        ```
    *   **Como instalar:** Se não tiver o Python ou tiver uma versão muito antiga, baixe o instalador mais recente em [python.org](https://www.python.org/downloads/windows/).
        > [!IMPORTANT] Durante a Instalação do Python
        > Marque a opção **"Add Python to PATH"** (ou "Adicionar Python ao PATH") durante o processo de instalação. Isso facilitará a execução de comandos Python e pip diretamente do terminal. Se você esqueceu de fazer isso, precisará adicionar manualmente os diretórios do Python e Scripts ao PATH do sistema.

2.  **pip (Gerenciador de Pacotes Python):**
    *   **Como verificar:** O pip geralmente é instalado automaticamente com o Python (a partir da versão 3.4). Verifique com:
        ```bash
        pip --version
        ```
    *   **Como atualizar (recomendado):**
        ```bash
        python -m pip install --upgrade pip
        ```

3.  **Git (Opcional, mas Altamente Recomendado):**
    *   **Utilidade:** Necessário para clonar o repositório do PraisonAI se você quiser acessar os exemplos mais recentes, contribuir para o projeto ou trabalhar com a versão de desenvolvimento.
    *   **Como instalar:** Baixe e instale o Git para Windows em [git-scm.com](https://git-scm.com/download/win).

## Configurando Variáveis de Ambiente

Para que o PraisonAI funcione corretamente, especialmente ao interagir com modelos de linguagem pagos (como os da OpenAI), você precisará configurar variáveis de ambiente. A mais comum é a `OPENAI_API_KEY`.

**Opção 1: Temporariamente (para a sessão atual do terminal)**

Abra o Prompt de Comando ou PowerShell e use o comando `set`:
```bash
set OPENAI_API_KEY=sua_chave_api_aqui
```
> [!WARNING] Chave Temporária
> Esta configuração será perdida quando você fechar o terminal.

**Opção 2: Permanentemente (para o usuário atual)**

Use o comando `setx`. Ele adiciona a variável permanentemente, mas você precisará abrir um **novo** terminal para que as alterações tenham efeito.
```bash
setx OPENAI_API_KEY "sua_chave_api_aqui"
```
> [!NOTE] Aspas em `setx`
> É uma boa prática usar aspas ao redor do valor da chave com `setx`, especialmente se ela contiver caracteres especiais (embora chaves de API geralmente não contenham).

**Opção 3: Permanentemente (via Interface Gráfica do Windows)**

1.  Pressione a tecla `Windows`, digite "variáveis de ambiente" e selecione "Editar as variáveis de ambiente do sistema".
2.  Na janela "Propriedades do Sistema", clique no botão "Variáveis de Ambiente...".
3.  Na seção "Variáveis de usuário para [Seu Nome de Usuário]", clique em "Novo...".
    *   **Nome da variável:** `OPENAI_API_KEY`
    *   **Valor da variável:** `sua_chave_api_aqui`
4.  Clique "OK" em todas as janelas. Você precisará abrir um novo terminal para que as alterações tenham efeito.

Outras variáveis de ambiente importantes, como `OPENAI_BASE_URL` (para usar com Ollama ou Groq), podem ser configuradas da mesma forma.

## Instalação do PraisonAI

Existem duas formas principais de instalar o PraisonAI:

### 1. Para Usuários (`praisonaiagents` e `praisonai` CLI)

Esta é a forma recomendada para a maioria dos usuários que desejam utilizar o PraisonAI para criar e executar agentes.

*   **`praisonaiagents` (Pacote leve para codificação):**
    Se você pretende principalmente usar o PraisonAI programaticamente em Python.
    ```bash
    pip install praisonaiagents
    ```

*   **`praisonai` (Pacote completo com CLI e modo "No Code"):**
    Se você quer a experiência completa, incluindo a interface de linha de comando (CLI) para executar arquivos YAML e o modo automático.
    ```bash
    pip install praisonai
    ```
    Este pacote geralmente inclui `praisonaiagents` como dependência.

### 2. Para Desenvolvedores (Trabalhando com o Código Fonte)

Se você pretende contribuir para o PraisonAI, modificar seu código-fonte ou usar as versões mais recentes diretamente do repositório.

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/MervinPraison/PraisonAI.git
    cd PraisonAI
    ```

2.  **Crie e Ative um Ambiente Virtual (Recomendado):**
    ```bash
    python -m venv .venv
    # No CMD:
    .venv\Scripts\activate
    # No PowerShell:
    .venv\Scripts\Activate.ps1
    ```

3.  **Instale `uv` (um instalador Python rápido):**
    O `README.md` do projeto sugere o uso de `uv`.
    ```bash
    pip install uv
    ```

4.  **Instale as dependências usando `uv`:**
    O PraisonAI usa `pyproject.toml` para gerenciar suas dependências.
    *   Instalação básica:
        ```bash
        uv pip install -e .
        ```
        O `-e .` instala o projeto em modo editável, o que significa que as alterações no código-fonte são refletidas imediatamente.

    *   Instalação com extras (para funcionalidades específicas como `code`, `crewai`, `autogen`):
        Consulte o arquivo `pyproject.toml` para ver os extras disponíveis. Exemplos:
        ```bash
        uv pip install -e .[code]
        uv pip install -e .[crewai,autogen]
        # Para instalar todos os extras, pode haver uma opção como [all] ou você precisará listá-los.
        # Verifique o pyproject.toml para a sintaxe correta dos extras.
        ```
        Alternativamente, se o `pyproject.toml` estiver configurado para isso, você pode instalar diretamente dele:
        ```bash
        uv pip install -r pyproject.toml --extra code
        ```

## Verificando a Instalação

Após a instalação, você pode verificar se tudo está funcionando corretamente.

**Se você instalou `praisonaiagents`:**

Crie um arquivo Python simples (ex: `teste_agente.py`):
```python
from praisonaiagents import Agent

try:
    # Certifique-se de ter sua OPENAI_API_KEY configurada como variável de ambiente
    agente_teste = Agent(instructions="Você é um assistente prestativo.")
    resposta = agente_teste.start("Escreva uma frase curta sobre IA.")
    print("Resposta do Agente:", resposta)
except Exception as e:
    print(f"Ocorreu um erro: {e}")
    print("Verifique se sua chave OPENAI_API_KEY está configurada corretamente.")
```
Execute-o:
```bash
python teste_agente.py
```

**Se você instalou `praisonai` (com CLI):**

Verifique a CLI:
```bash
praisonai --version
```
Tente o modo automático (requer `OPENAI_API_KEY`):
```bash
praisonai --auto "Conte uma piada curta sobre programadores"
```

## Solução de Problemas Comuns (Windows)

*   **`pip` ou `python` não é reconhecido como um comando:**
    *   **Causa:** Python não foi adicionado ao PATH durante a instalação.
    *   **Solução:** Reinstale o Python marcando "Add Python to PATH" ou adicione manualmente os diretórios `C:\Users\SEU_USUARIO\AppData\Local\Programs\Python\PythonXX` e `C:\Users\SEU_USUARIO\AppData\Local\Programs\Python\PythonXX\Scripts` às Variáveis de Ambiente do sistema. (Substitua `SEU_USUARIO` e `PythonXX` conforme sua instalação).

*   **Erro ao instalar pacotes com `pip` (ex: erros de compilação):**
    *   **Causa:** Alguns pacotes Python podem ter dependências que requerem ferramentas de compilação C/C++ (Microsoft Visual C++ Build Tools).
    *   **Solução:** Instale as "Build Tools for Visual Studio" do site da Microsoft. Geralmente, selecionar a carga de trabalho "Desenvolvimento para desktop com C++" é suficiente.

*   **Permissões:**
    *   **Causa:** Em alguns casos, você pode precisar de permissões de administrador para instalar pacotes globalmente (não recomendado) ou para modificar certas pastas.
    *   **Solução:** Prefira usar ambientes virtuais. Se realmente precisar, execute o Prompt de Comando ou PowerShell como Administrador.

*   **Conflitos de Pacotes:**
    *   **Causa:** Versões incompatíveis de pacotes.
    *   **Solução:** Use ambientes virtuais para isolar as dependências de cada projeto. Comandos como `pip freeze > requirements.txt` e `pip install -r requirements.txt` ajudam a gerenciar dependências.

Com este guia, você deve ser capaz de instalar o PraisonAI em seu sistema Windows e começar sua jornada no desenvolvimento de agentes de IA!
