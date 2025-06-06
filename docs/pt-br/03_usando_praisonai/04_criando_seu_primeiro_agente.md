# Criando Seu Primeiro Agente

Este guia prático mostra passo a passo como colocar um agente PraisonAI em funcionamento usando Python. Se você já instalou o pacote `praisonaiagents`, siga em frente.

## 1. Configure o Ambiente

1. Abra um terminal e crie uma pasta para seus testes:
   ```bash
   mkdir meu_primeiro_agente
   cd meu_primeiro_agente
   ```
2. (Opcional) Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # No Windows use `.venv\Scripts\activate`
   ```
3. Instale o pacote se ainda não o fez:
   ```bash
   pip install praisonaiagents
   ```

## 2. Escreva o Código do Agente

Crie um arquivo `roteirista.py` com o seguinte conteúdo:

```python
from praisonaiagents import Agent

agente = Agent(
    instructions="Você é um roteirista de cinema muito criativo.",
    role="Roteirista",
    goal="Escrever um pequeno roteiro sobre robôs em Marte."
)

resultado = agente.start("Crie o roteiro com três cenas principais.")
print(resultado)
```

## 3. Execute e Analise

No terminal, rode:
```bash
python roteirista.py
```

O PraisonAI conectará ao modelo LLM configurado (por padrão OpenAI) e exibirá o roteiro gerado.

- Se estiver tudo certo, experimente alterar as instruções, o papel ou o objetivo e observe como o resultado muda.
- Consulte [Usando o PraisonAI com Python](01_usando_com_python.md) para entender todos os parâmetros disponíveis.

## 4. Próximos Passos

Depois de dominar este exemplo simples, explore:
- [Criando múltiplos agentes](01_usando_com_python.md#criando-múltiplos-agentes-multi-agents)
- [Definindo agentes via YAML](02_usando_com_yaml.md)
- Os notebooks em `examples/python/` para casos de uso completos.

Bom aprendizado!
