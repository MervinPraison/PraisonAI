# Configurações com YAML

Os arquivos YAML permitem definir agentes, tarefas e parâmetros do PraisonAI de forma declarativa. Eles são utilizados principalmente pela CLI `praisonai` para iniciar fluxos complexos sem escrever código Python.

## Estrutura Básica

Um YAML comum segue o formato visto em `src/praisonai/agents.yaml`:

```yaml
framework: praisonai
process: sequential
topic: exemplo de topico
memory: false
roles:
  pesquisador:
    role: Researcher
    goal: Obter informações sobre o tema
    tasks:
      pesquisa:
        description: Realizar buscas e resumir resultados
        expected_output: Relatório da pesquisa
    tools:
      - search_tool
dependencies: []
```

### Principais Campos

- **framework**: define qual biblioteca será usada (“praisonai”, “crewai” ou “autogen”).
- **process**: forma de execução (sequencial, paralelo etc.).
- **topic**: assunto ou objetivo geral dos agentes.
- **memory**: habilita ou não memória.
- **roles**: cada agente é descrito aqui com suas tarefas e ferramentas.
- **dependencies**: lista de tarefas que dependem de outras.

## Arquivos Avançados

O `agents-advanced.yaml` demonstra configurações mais complexas, como uso de modelos diferentes para cada agente e escrita de saída em arquivos.

Explore esses arquivos na pasta `src/praisonai` para entender como adaptar às suas necessidades. Após ajustar o YAML, execute:

```bash
praisonai caminho/do/arquivo.yaml
```

Isso carregará as configurações e iniciará o fluxo definido.
