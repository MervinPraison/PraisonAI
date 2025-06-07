# Workflows Avançados: Agentes Repetitivos (Repetitive Agents)

O padrão de **Agentes Repetitivos (Repetitive Agents)** refere-se a um workflow onde um ou mais agentes são projetados para executar uma tarefa específica (ou um conjunto de tarefas) múltiplas vezes, geralmente sobre diferentes conjuntos de dados de entrada ou até que uma determinada condição seja satisfeita.

Este padrão é útil para automação de processos que envolvem a aplicação da mesma lógica a vários itens ou para tarefas que requerem monitoramento ou ação contínua.

## Como Funcionam os Agentes Repetitivos?

1.  **Definição da Tarefa:** Uma tarefa ou um conjunto de tarefas que o agente precisa realizar é claramente definida.
2.  **Entrada de Dados (Iterável):** Há uma fonte de dados ou um gatilho que fornece a entrada para cada iteração. Pode ser:
    *   Uma lista de itens (ex: URLs, nomes de arquivos, registros de um banco de dados).
    *   Um fluxo de dados contínuo (ex: novos e-mails chegando, atualizações de um feed).
    *   Um contador ou uma condição de tempo (ex: executar a cada hora).
3.  **Loop de Execução:** O agente (ou o sistema que o gerencia) entra em um loop:
    *   **Obter Entrada:** Pega o próximo item da lista, lê do fluxo, ou verifica a condição de tempo/evento.
    *   **Executar Tarefa:** O agente executa sua tarefa definida usando a entrada atual.
    *   **Produzir Saída/Efeito Colateral:** O agente gera um resultado para a iteração atual ou realiza uma ação (ex: salva um arquivo, envia uma notificação).
4.  **Condição de Parada:** O loop continua até que:
    *   Todos os itens da lista tenham sido processados.
    *   O fluxo de dados termine.
    *   Uma condição específica de parada seja atingida (ex: um erro crítico, um sinal do usuário, um número máximo de iterações).

**Diagrama (do `README.md` do PraisonAI):**
\`\`\`mermaid
flowchart LR
    EntradaIteravel[Entrada / Lista de Itens / Gatilho] --> AgenteLoop[("Agente em Loop")]
    AgenteLoop -- Processa Item/Evento --> Tarefa[Executa Tarefa Definida]
    Tarefa -- Para Próxima Iteração / Item --> AgenteLoop
    Tarefa -- Concluído / Condição de Parada --> Saida[Saída Agregada / Fim do Processo]

    style EntradaIteravel fill:#8B0000,color:#fff
    style AgenteLoop fill:#2E8B57,color:#fff,shape:circle
    style Tarefa fill:#189AB4,color:#fff
    style Saida fill:#8B0000,color:#fff
\`\`\`

## Casos de Uso

*   **Processamento em Lote de Arquivos:**
    *   Agente lê cada arquivo de uma pasta, extrai informações e salva em um banco de dados.
*   **Web Scraping de Múltiplas Páginas:**
    *   Agente recebe uma lista de URLs, visita cada uma, extrai dados específicos e os armazena.
*   **Envio de E-mails Personalizados em Massa:**
    *   Agente percorre uma lista de contatos, personaliza um template de e-mail para cada um e o envia.
*   **Monitoramento e Alerta:**
    *   Agente verifica o status de um sistema a cada X minutos e envia um alerta se detectar um problema.
*   **Tradução de Múltiplos Documentos:**
    *   Agente traduz uma série de documentos de um idioma para outro.
*   **Classificação de Dados:**
    *   Agente analisa uma lista de comentários de clientes e classifica cada um como positivo, negativo ou neutro.

## Implementação no PraisonAI (Conceitual)

A implementação de agentes repetitivos no PraisonAI pode ser feita de várias formas:

1.  **Loop de Controle Externo (Python):**
    *   Você pode escrever um script Python que define um agente PraisonAI e, em seguida, usa um loop `for` ou `while` para chamar o método `start()` (ou similar) do agente repetidamente com diferentes dados de entrada.

    **Exemplo Python Conceitual:**
    \`\`\`python
    from praisonaiagents import Agent

    # Supondo que OPENAI_API_KEY está configurada
    tradutor_agente = Agent(
        instructions="Traduza o seguinte texto para o espanhol: {texto_para_traduzir}",
        role="Tradutor Inglês-Espanhol"
    )

    lista_de_frases_ingles = [
        "Hello, world!",
        "How are you?",
        "This is a test."
    ]

    traducoes_espanhol = []

    for frase in lista_de_frases_ingles:
        # A forma de passar o input pode variar.
        # Idealmente, o agente é configurado para esperar uma variável no prompt.
        # Se o método start apenas concatena, você faria:
        # traducao = tradutor_agente.start(f"Traduza o seguinte texto para o espanhol: {frase}")
        # Mas se o Agent suportar substituição de placeholders nas instructions:
        traducao = tradutor_agente.start(texto_para_traduzir=frase)
        traducoes_espanhol.append(traducao)
        print(f"Inglês: {frase} -> Espanhol: {traducao}")

    # print("\nTraduções Finais:", traducoes_espanhol)
    \`\`\`

2.  **Agente com Capacidade de Iteração Interna (Menos Comum para LLMs):**
    *   Seria menos comum que um agente baseado em LLM gerenciasse um loop complexo internamente apenas com prompts, a menos que ele estivesse escrevendo e executando código que implementasse o loop.
    *   No entanto, um agente poderia ser instruído a processar uma *lista* de itens fornecida em um único prompt, se a lista não for muito grande. Ex: "Traduza as seguintes 3 frases: [frase1, frase2, frase3]".

3.  **Workflows YAML com Gatilhos ou Fontes de Dados Iteráveis:**
    *   Se o PraisonAI (ou o framework subjacente como AutoGen) suportar gatilhos baseados em tempo (agendamento) ou a capacidade de ler de uma fonte de dados que pode ser iterada (ex: um arquivo CSV, uma fila de mensagens), então o workflow YAML poderia ser configurado para executar repetidamente.
    *   O `schedule_config.yaml.example` no repositório PraisonAI sugere capacidades de agendamento, o que se alinha com tarefas repetitivas.

    **Exemplo YAML Conceitual (para um agendador hipotético):**
    \`\`\`yaml
    # Supondo uma configuração de agendamento no PraisonAI
    schedule:
      - name: "verificar_novos_pedidos_a_cada_5_minutos"
        cron_expression: "*/5 * * * *" # A cada 5 minutos
        workflow_yaml: "workflows/processar_pedido.yaml" # YAML que define o agente e a tarefa de processar um pedido
        # input_source: "fila_de_pedidos_api" # De onde pegar o dado do pedido
    \`\`\`

4.  **Uso de Ferramentas que Gerenciam Iteração:**
    *   O agente pode ter uma ferramenta que, quando chamada, processa uma coleção de itens. Por exemplo, uma ferramenta `processar_lista_de_urls(urls: list)` que internamente itera sobre as URLs e realiza uma ação para cada uma.

## Considerações para Agentes Repetitivos

*   **Gerenciamento de Estado entre Iterações:** Se o agente precisa lembrar informações de iterações anteriores (além do contexto de curto prazo), a [memória](./../02_conceitos_fundamentais/05_memoria.md) persistente é crucial.
*   **Tratamento de Erros:** Em um loop longo, é importante ter um bom tratamento de erros. O que acontece se uma iteração falhar? O loop para? A falha é registrada e o loop continua?
*   **Eficiência e Custo:** Executar um agente LLM muitas vezes pode ser lento e/ou caro. Para tarefas repetitivas muito simples, pode haver soluções não-LLM mais eficientes. Considere otimizações como:
    *   Usar LLMs menores e mais rápidos se a tarefa permitir.
    *   Processamento em lote (batching) de chamadas LLM, se possível.
    *   Paralelização (se as iterações forem independentes).
*   **Limites de Taxa (Rate Limiting):** Cuidado com os limites de taxa das APIs dos LLMs ou outras APIs que suas ferramentas possam estar usando.
*   **Idempotência:** Se possível, projete a tarefa do agente para ser idempotente, o que significa que executá-la múltiplas vezes com a mesma entrada produz o mesmo resultado ou não causa efeitos colaterais indesejados. Isso é útil se uma iteração precisar ser re-executada devido a uma falha.

Os Agentes Repetitivos são um padrão essencial para automatizar tarefas que precisam ser aplicadas a múltiplos conjuntos de dados ou executadas de forma contínua. O PraisonAI fornece a flexibilidade para implementar este padrão, seja através de loops de controle externos em Python ou potencialmente através de configurações de workflow mais avançadas.

Com este tópico, concluímos a exploração dos principais padrões de Workflows Avançados ilustrados no PraisonAI!
