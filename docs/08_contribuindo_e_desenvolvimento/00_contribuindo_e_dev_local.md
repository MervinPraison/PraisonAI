# TODO: Translate this file to English

# Módulo: Contribuindo para o PraisonAI e Desenvolvimento Local

Este módulo é para você que deseja ir além de usar o PraisonAI e quer contribuir para o seu desenvolvimento, ou simplesmente configurar um ambiente local para explorar o código-fonte mais a fundo e talvez fazer suas próprias modificações.

## Contribuindo para o PraisonAI

Contribuições da comunidade são essenciais para o crescimento e aprimoramento de projetos de código aberto como o PraisonAI. Se você tem interesse em contribuir, o processo geralmente segue o fluxo padrão do GitHub:

1.  **Faça um Fork do Repositório:**
    *   Vá até a página do repositório oficial do PraisonAI no GitHub: [https://github.com/MervinPraison/PraisonAI](https://github.com/MervinPraison/PraisonAI)
    *   Clique no botão "Fork" no canto superior direito. Isso criará uma cópia do repositório na sua conta do GitHub.

2.  **Clone o Seu Fork Localmente:**
    *   Em seu terminal, clone o repositório que você acabou de "forkar":
        ```bash
        git clone https://github.com/SEU_USUARIO_GITHUB/PraisonAI.git
        cd PraisonAI
        ```
    *   Substitua `SEU_USUARIO_GITHUB` pelo seu nome de usuário no GitHub.

3.  **Crie uma Nova Branch para Suas Mudanças:**
    *   É uma boa prática criar uma nova branch para cada funcionalidade ou correção que você for trabalhar. Isso mantém o histórico organizado e facilita a integração.
        ```bash
        git checkout -b minha-nova-funcionalidade # Escolha um nome descritivo para a branch
        ```

4.  **Faça Suas Alterações:**
    *   Implemente a nova funcionalidade, corrija um bug, melhore a documentação, etc.
    *   Certifique-se de seguir as convenções de código e estilo do projeto, se houver.

5.  **Teste Suas Mudanças:**
    *   Execute os testes existentes para garantir que suas alterações não quebraram nada. (Veja a seção "Executando Testes" abaixo).
    *   Se estiver adicionando uma nova funcionalidade, considere adicionar novos testes para cobri-la.

6.  **Faça o Commit das Suas Alterações:**
    *   Adicione os arquivos modificados e faça o commit com uma mensagem clara e descritiva.
        ```bash
        git add .
        git commit -m "feat: Adiciona nova funcionalidade X que faz Y"
        # Ou "fix: Corrige bug Z no componente W"
        # Siga as convenções de commit do projeto, se houver (ex: Conventional Commits).
        ```

7.  **Envie Suas Alterações para o Seu Fork no GitHub:**
    ```bash
    git push origin minha-nova-funcionalidade
    ```

8.  **Abra um Pull Request (PR):**
    *   Vá até a página do seu fork no GitHub.
    *   Você verá um aviso para criar um Pull Request da sua nova branch para o repositório original do PraisonAI.
    *   Clique nele, revise suas alterações, escreva uma descrição clara do que seu PR faz e porquê, e envie-o.

9.  **Aguarde o Feedback:**
    *   Os mantenedores do projeto revisarão seu Pull Request. Eles podem solicitar alterações, fazer perguntas ou aprovar e mesclar suas contribuições. Seja paciente e responsivo ao feedback.

**Onde mais procurar por informações sobre contribuição:**
*   Verifique se há um arquivo `CONTRIBUTING.md` no repositório principal.
*   Observe as issues abertas, especialmente aquelas marcadas como "good first issue" ou "help wanted".
*   Participe das discussões da comunidade (links geralmente no `README.md` ou na página do GitHub).

## Configurando o Ambiente de Desenvolvimento Local

Se você deseja explorar o código, fazer modificações ou contribuir, precisará de um ambiente de desenvolvimento local.

1.  **Pré-requisitos:**
    *   Python (versão >=3.10, conforme `pyproject.toml`).
    *   Git.
    *   Opcional, mas recomendado: `uv` (um instalador Python rápido).

2.  **Clone o Repositório (se ainda não o fez):**
    ```bash
    git clone https://github.com/MervinPraison/PraisonAI.git # Ou seu fork
    cd PraisonAI/src/praisonai # Navegue para a pasta do pacote principal que contém o pyproject.toml
    ```
    *Nota: O `pyproject.toml` principal do projeto parece estar em `src/praisonai/`. Verifique a estrutura exata se tiver problemas.*

3.  **Crie e Ative um Ambiente Virtual (Altamente Recomendado):**
    Isso isola as dependências do projeto e evita conflitos com outros projetos Python em seu sistema.
    ```bash
    # Navegue para a pasta que contém o pyproject.toml (ex: src/praisonai)
    python -m venv .venv
    # No Windows (CMD):
    # .venv\Scripts\activate
    # No Windows (PowerShell):
    # .venv\Scripts\Activate.ps1
    # No macOS/Linux:
    # source .venv/bin/activate
    ```

4.  **Instale `uv` (Recomendado pelo Projeto):**
    Se ainda não o tiver e quiser seguir as instruções de desenvolvimento do `README.md`:
    ```bash
    pip install uv
    ```

5.  **Instale as Dependências do Projeto:**
    O `README.md` e o `pyproject.toml` do PraisonAI indicam o uso de `uv` para instalar dependências.
    *   **Instalação básica em modo editável (para desenvolvimento):**
        Isto instalará o pacote `PraisonAI` e suas dependências principais. O modo editável (`-e`) significa que as alterações que você fizer no código-fonte local serão refletidas imediatamente ao usar o pacote.
        ```bash
        # Certifique-se de estar na pasta com o pyproject.toml (ex: src/praisonai)
        uv pip install -e .
        ```
    *   **Instalando com dependências opcionais (extras):**
        O PraisonAI usa "extras" para dependências que habilitam funcionalidades específicas (como `crewai`, `autogen`, `ui`, `code`, etc.). Você pode instalá-los conforme necessário.
        ```bash
        uv pip install -e .[crewai,autogen]
        uv pip install -e .[ui,code]
        # Para instalar todos os extras, você pode precisar listá-los ou verificar se há um extra "all".
        # O pyproject.toml lista os extras disponíveis.
        ```
        O `README.md` também menciona:
        ```bash
        # uv pip install -r pyproject.toml --extra code
        # Esta sintaxe também pode funcionar, mas instalar com -e .[extra] é comum para desenvolvimento local.
        ```
        A forma mais idiomática, especialmente com `uv` e Poetry (que o `pyproject.toml` usa), seria instalar os grupos de dependência. O `pyproject.toml` define grupos como `[tool.poetry.group.dev.dependencies]`.
        Para instalar dependências de desenvolvimento (que incluem testes, docs, etc.):
        ```bash
        uv pip install --system # Garante que uv use o Python do ambiente virtual ativo
        uv pip install -e .[dev] # Se houver um extra 'dev' que agrupe tudo
        # Ou, se usando Poetry diretamente (não uv):
        # poetry install --with dev
        ```
        Dado que o `README.md` foca em `uv pip install -r pyproject.toml --extra <nome>` ou `uv pip install -e .[<extra>]`, siga essa orientação.

## Executando Testes

O PraisonAI possui uma estrutura de testes abrangente, conforme detalhado em `src/praisonai/tests/TESTING_GUIDE.md`. É crucial executar testes após fazer alterações para garantir que nada foi quebrado.

**Principais Pontos do Guia de Testes:**

*   **Estrutura:**
    *   `tests/unit/`: Testes unitários (rápidos, isolados).
    *   `tests/integration/`: Testes de integração mockados (gratuitos, rápidos, para CI/CD e desenvolvimento).
    *   `tests/e2e/`: Testes end-to-end reais (podem ter custos com APIs, mais lentos).
*   **Como Rodar (Recomendado pelo `TESTING_GUIDE.md`):**
    O projeto fornece um `test_runner.py`.
    *   **Testes Mock (Gratuitos):**
        ```bash
        # Todos os testes de integração mockados
        python tests/test_runner.py --pattern frameworks

        # Testes mock apenas para AutoGen
        python tests/test_runner.py --pattern autogen

        # Testes mock apenas para CrewAI
        python tests/test_runner.py --pattern crewai
        ```
    *   **Testes Reais (Podem ter Custo!):**
        Requerem configuração de chaves de API (ex: `OPENAI_API_KEY`).
        ```bash
        # Todos os testes reais (irá pedir confirmação)
        python tests/test_runner.py --pattern real
        ```
        (Existem mais padrões para testes reais e de execução completa, consulte o `TESTING_GUIDE.md`).
*   **Usando `pytest` Diretamente:**
    O `pyproject.toml` lista `pytest` como uma dependência de teste.
    *   **Testes de Integração Mockados:**
        ```bash
        # Certifique-se de que as dependências de teste estão instaladas no seu ambiente virtual
        # (ex: uv pip install -e .[test] ou poetry install --with test)
        python -m pytest src/praisonai/tests/integration/ -v
        # Ou pytest src/praisonai/tests/integration/ -v (se pytest está no PATH do venv)
        ```
    *   **Testes Reais (Requer Chaves de API):**
        ```bash
        python -m pytest src/praisonai/tests/e2e/ -v -m real
        ```

**Antes de rodar testes reais, sempre leia o `TESTING_GUIDE.md` para entender os custos potenciais e a configuração necessária.**

Seguindo estas diretrizes, você estará bem equipado para contribuir com o PraisonAI ou para explorá-lo e adaptá-lo às suas necessidades em um ambiente de desenvolvimento local.
