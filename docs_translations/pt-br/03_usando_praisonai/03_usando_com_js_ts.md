# Usando o PraisonAI com JavaScript e TypeScript

PraisonAI também oferece suporte para desenvolvimento de agentes de IA usando JavaScript e TypeScript através do pacote `praisonai` no npm. Isso permite que desenvolvedores front-end e back-end que trabalham com o ecossistema Node.js integrem o poder do PraisonAI em suas aplicações.

## Configuração Inicial

1.  **Node.js e npm/yarn:** Certifique-se de ter o Node.js instalado. O npm (Node Package Manager) vem com o Node.js. Se preferir, você pode usar o yarn.
    *   Para verificar:
        ```bash
        node -v
        npm -v
        ```
    *   Download Node.js: [nodejs.org](https://nodejs.org/)

2.  **Instale o pacote `praisonai`:**
    *   Com npm:
        ```bash
        npm install praisonai
        ```
    *   Com yarn:
        ```bash
        yarn add praisonai
        ```

3.  **Configure sua Chave de API:**
    Assim como na versão Python, você precisará de uma chave de API para o provedor de LLM que pretende usar (ex: OpenAI). Configure-a como uma variável de ambiente:
    ```bash
    export OPENAI_API_KEY=sua_chave_api_aqui
    ```
    Em ambientes de produção Node.js, você pode usar pacotes como `dotenv` para gerenciar variáveis de ambiente a partir de um arquivo `.env`.

## Usando com JavaScript (CommonJS ou ES Modules)

O `README.md` principal do PraisonAI mostra um exemplo simples em JavaScript (CommonJS):

**Exemplo JavaScript (CommonJS - `app.js`):**
```javascript
const { Agent } = require('praisonai'); // Importa a classe Agent

// Cria uma instância do Agente
const agent = new Agent({
  instructions: 'Você é um assistente de IA prestativo.'
  // Você pode adicionar outras configurações aqui, como:
  // role: "Escritor Criativo",
  // goal: "Escrever uma história curta",
  // llm: { provider: "openai", model: "gpt-3.5-turbo" } // Exemplo de configuração de LLM
});

// Define a tarefa/prompt e inicia o agente
async function runAgent() {
  try {
    const result = await agent.start('Escreva um roteiro de filme sobre um robô em Marte.');
    console.log(result);
  } catch (error) {
    console.error("Erro ao executar o agente:", error);
  }
}

runAgent();
```

**Para executar (CommonJS):**
```bash
node app.js
```

Se estiver usando ES Modules em seu projeto Node.js (com `"type": "module"` no seu `package.json` ou usando a extensão `.mjs`):

**Exemplo JavaScript (ES Modules - `app.mjs`):**
```javascript
import { Agent } from 'praisonai'; // Importa a classe Agent

const agent = new Agent({
  instructions: 'Você é um assistente de IA prestativo.'
});

async function runAgent() {
  try {
    const result = await agent.start('Escreva um roteiro de filme sobre um robô em Marte.');
    console.log(result);
  } catch (error)
    console.error("Erro ao executar o agente:", error);
  }
}

runAgent();
```

**Para executar (ES Modules):**
```bash
node app.mjs
```

## Usando com TypeScript

TypeScript adiciona tipagem estática ao JavaScript, o que pode ajudar a pegar erros mais cedo e melhorar a manutenibilidade do código. O PraisonAI também suporta TypeScript.

1.  **Instale o TypeScript e tipos (se necessário):**
    ```bash
    npm install -D typescript @types/node
    # ou
    yarn add -D typescript @types/node
    ```

2.  **Crie um arquivo `tsconfig.json` (se não tiver):**
    ```bash
    npx tsc --init
    ```
    Ajuste as configurações no `tsconfig.json` conforme necessário (ex: `target`, `module`, `outDir`).

**Exemplo TypeScript (`app.ts`):**
```typescript
import { Agent, AgentConfig } from 'praisonai'; // Importa Agent e o tipo de configuração

const agentConfig: AgentConfig = {
  instructions: 'Você é um escritor criativo que escreve contos com emojis.',
  role: "Contador de Histórias com Emojis",
  goal: "Escrever uma história curta e divertida sobre um tema dado, usando emojis apropriados.",
  // llm: { provider: "openai", model: "gpt-4" } // Exemplo
};

const agent = new Agent(agentConfig);

async function runAgent(): Promise<void> {
  try {
    const storyPrompt: string = "Escreva uma história sobre um viajante do tempo que visita dinossauros.";
    const result: string | undefined = await agent.start(storyPrompt); // O resultado pode ser string ou undefined
    if (result) {
      console.log("História Gerada:");
      console.log(result);
    } else {
      console.log("O agente não retornou um resultado.");
    }
  } catch (error) {
    console.error("Erro ao executar o agente:", error);
  }
}

runAgent();
```

**Para compilar e executar (TypeScript):**

1.  Compile o código TypeScript para JavaScript:
    ```bash
    npx tsc
    ```
    Isso criará um arquivo `app.js` no seu diretório de saída (ex: `dist/app.js`).

2.  Execute o arquivo JavaScript compilado:
    ```bash
    node dist/app.js
    ```

    Alternativamente, você pode usar `ts-node` para executar diretamente arquivos TypeScript (ótimo para desenvolvimento):
    ```bash
    npm install -D ts-node
    # ou
    yarn add -D ts-node

    npx ts-node app.ts
    ```

## Funcionalidades e Limitações

A versão JavaScript/TypeScript do PraisonAI visa espelhar a funcionalidade da versão Python, permitindo:

*   Criação de agentes com instruções, papéis, objetivos.
*   Configuração de LLMs.
*   Execução de tarefas.
*   Potencialmente, uso de ferramentas e memória (verifique a documentação da API JS para detalhes sobre a paridade de recursos com a versão Python).

**Onde encontrar mais detalhes:**

*   **Repositório PraisonAI (`src/praisonai-ts/`):** A pasta `src/praisonai-ts/` no repositório principal do PraisonAI contém o código-fonte da biblioteca TypeScript. Dentro dela, a subpasta `examples/` é particularmente útil:
    *   `src/praisonai-ts/examples/simple/`: Contém exemplos básicos.
    *   `src/praisonai-ts/examples/tools/`: Pode conter exemplos de como usar ferramentas.
    *   `src/praisonai-ts/examples/concepts/`: Pode ilustrar conceitos como memória ou workflows.
*   **Documentação Oficial (`docs.praison.ai`):** Embora a documentação possa focar mais na versão Python e YAML, procure por seções específicas sobre JavaScript/TypeScript ou referências à API JS.

**Considerações:**

*   **Paridade de Recursos:** É comum que bibliotecas com versões em múltiplas linguagens tenham uma pequena defasagem de recursos entre elas, com a versão principal (neste caso, Python) geralmente sendo a mais completa inicialmente. Sempre verifique a documentação específica da API JavaScript/TypeScript do PraisonAI para confirmar as funcionalidades disponíveis.
*   **Ecossistema Node.js:** Ao usar PraisonAI com JavaScript/TypeScript, você pode aproveitar todo o ecossistema Node.js, incluindo seus frameworks web (Express, NestJS), bibliotecas e ferramentas de desenvolvimento.

Esta introdução deve ajudá-lo a começar a usar o PraisonAI em seus projetos JavaScript e TypeScript. A exploração dos exemplos no repositório é altamente recomendada para entender melhor as capacidades e a API da versão JS/TS.
