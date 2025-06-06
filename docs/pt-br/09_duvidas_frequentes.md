# Dúvidas Frequentes (FAQ)

Esta seção reúne respostas rápidas para questões comuns ao começar com o PraisonAI.

## 1. "ModuleNotFoundError: praisonaiagents"
Se, ao executar um exemplo em Python, você receber essa mensagem:
```bash
ModuleNotFoundError: No module named 'praisonaiagents'
```
Isso indica que o pacote não está instalado no ambiente atual. Execute:
```bash
pip install praisonaiagents
```
Se estiver usando um clone do repositório, você também pode instalar em modo editável:
```bash
uv pip install -e .
```
(caso tenha o `uv` instalado) ou
```bash
pip install -e .
```

## 2. Como configuro minha `OPENAI_API_KEY`?
A maioria dos exemplos utiliza modelos da OpenAI. Defina a variável de ambiente com:
```bash
export OPENAI_API_KEY="sua-chave-aqui"  # Linux ou macOS
set OPENAI_API_KEY="sua-chave-aqui"      # Windows CMD
$env:OPENAI_API_KEY="sua-chave-aqui"     # PowerShell
```

## 3. Preciso de GPU ou conexão constante com a internet?
Para executar os agentes locais que usam modelos via API (como OpenAI), basta ter conexão com a internet. Uma GPU dedicada só é necessária se você planeja rodar modelos locais pesados (ex.: via Ollama ou outros provedores que permitam modelos offline).

## 4. Onde ficam os exemplos prontos?
Todos os scripts demonstrativos estão em `examples/python/`. A pasta é subdividida em:
- `agents/` – agentes especializados (veja [Modelos de Agentes](03_usando_praisonai/05_modelos_de_agentes.md)).
- `general/` – conceitos isolados como memória, ferramentas e workflows.
- `concepts/` – implementações de RAG, processamento de CSV etc.
- `usecases/` – estudos de caso completos.

Abra um terminal nesse diretório e execute o arquivo desejado com `python nome_do_exemplo.py`.

## 5. Como tiro outras dúvidas ou reporto problemas?
Consulte o repositório no GitHub e abra uma *issue* descrevendo o problema ou a sugestão. Se preferir discutir em português, sinta-se à vontade.

