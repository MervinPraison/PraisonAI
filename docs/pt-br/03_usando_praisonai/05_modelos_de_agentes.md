# Modelos de Agentes Disponíveis

Esta seção apresenta um resumo dos modelos de agentes fornecidos como exemplos no PraisonAI. Eles servem como ponto de partida para criar soluções adaptadas às suas necessidades.

Cada agente abaixo possui um script dedicado em `examples/python/agents/`. A execução parte do mesmo princípio: instale o pacote `praisonaiagents`, configure sua chave de API do modelo de linguagem e rode o arquivo Python correspondente.

## Agentes Especializados

### 1. Agente Analista de Dados
Arquivo: `data-analyst-agent.py`

Utiliza ferramentas de manipulação de CSV/Excel para ler, filtrar, agrupar e gerar insights de dados.
Execute:
```bash
python data-analyst-agent.py
```

### 2. Agente Financeiro
Arquivo: `finance-agent.py`

Consulta preços, informações e histórico de ações. Útil para análises de mercado básicas.
```bash
python finance-agent.py
```

### 3. Agente de Pesquisa
Arquivo: `research-agent.py`

Realiza buscas na web com `duckduckgo` e retorna resultados resumidos.
```bash
python research-agent.py
```

### 4. Agente de Planejamento
Arquivo: `planning-agent.py`

Ajuda a planejar viagens ou atividades pesquisando informações relevantes on-line.
```bash
python planning-agent.py
```

### 5. Agente de Recomendação
Arquivo: `recommendation-agent.py`

Gera recomendações (como filmes) a partir de buscas na web e de conhecimento prévio do LLM.
```bash
python recommendation-agent.py
```

### 6. Agente de Compras
Arquivo: `shopping-agent.py`

Pesquisa produtos em diferentes sites e organiza os preços em formato de tabela.
```bash
python shopping-agent.py
```

### 7. Agente de Programação
Arquivo: `programming-agent.py`

Contém ferramentas para execução de código, análise, formatação e acesso ao shell. Permite iterar no desenvolvimento de scripts.
```bash
python programming-agent.py
```

### 8. Agente de Markdown
Arquivo: `markdown-agent.py`

Gera ou transforma textos em Markdown.
```bash
python markdown-agent.py
```

### 9. Agente de Busca na Web
Arquivo: `websearch-agent.py`

Focado em pesquisas rápidas na internet.
```bash
python websearch-agent.py
```

### 10. Agente Wikipedia
Arquivo: `wikipedia-agent.py`

Consulta a Wikipedia para reunir informações detalhadas sobre um tópico.
```bash
python wikipedia-agent.py
```

### 11. Agente SearxNG
Arquivo: `searxng-agent.py`

Realiza buscas através de uma instância SearxNG (pode ser container Docker). Necessita do serviço rodando localmente.
```bash
python searxng-agent.py
```

### 12. Agente de Imagens
Arquivo: `image-agent.py`

Aplica análise de imagens, podendo lidar tanto com URLs quanto com arquivos locais.
```bash
python image-agent.py
```

### 13. Agente de Imagem para Texto
Arquivo: `image-to-text-agent.py`

Semelhante ao agente de imagens, mas com foco em descrever conteúdo visual (OCR/descrição). Execute:
```bash
python image-to-text-agent.py
```

### 14. Agente de Vídeo
Arquivo: `video-agent.py`

Permite fornecer arquivos de vídeo para extração de informações e resumo de eventos.
```bash
python video-agent.py
```

### 15. Agente "Single"
Arquivo: `single-agent.py`

Exemplo básico de um agente único com prompt simples. Ótimo ponto de partida.
```bash
python single-agent.py
```

## Dicas Gerais

1. Abra um terminal na pasta `examples/python/agents`.
2. Ative seu ambiente virtual (se usar).
3. Execute o arquivo desejado conforme mostrado acima.
4. Explore e modifique os scripts para entender como cada agente opera.

Com essas bases, você pode combinar os agentes ou adaptá-los para criar soluções personalizadas no PraisonAI.
