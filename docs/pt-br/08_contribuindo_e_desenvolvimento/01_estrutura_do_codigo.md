# Entendendo a Estrutura do Código

Para contribuir ou personalizar o PraisonAI é importante conhecer a organização do diretório `src/`.

## Principais Pastas

- **praisonai/**: pacote Python que oferece a CLI `praisonai` e arquivos de configuração de exemplo (`agents.yaml`, `agents-advanced.yaml`, `config.yaml`). É aqui que está o script `cli.py` com as funções de execução e deploy.
- **praisonai-agents/**: biblioteca central `praisonaiagents` contendo as classes `Agent`, `Task`, memórias e ferramentas nativas.
- **praisonai-ts/**: versão em TypeScript/Node.js do framework, destinada a quem prefere trabalhar em JavaScript.

Dentro de cada pacote há submódulos como `agent`, `task`, `memory`, `tools` e `llm`. Explore esses arquivos para entender como os agentes são implementados.

### Arquivos de Configuração

Na pasta `src/praisonai` você encontra exemplos de YAML prontos (citados no módulo [Configurações com YAML](../03_usando_praisonai/06_configuracoes_yaml.md)). Esses arquivos são ótimos pontos de partida para seus experimentos.

Além disso, o script `inc/config.py` possui a função `generate_config`, utilizada para criar `config.yaml` com parâmetros de treinamento.

Conhecer essa estrutura ajuda a localizar facilmente onde adicionar novos agentes, ferramentas ou integrações.
