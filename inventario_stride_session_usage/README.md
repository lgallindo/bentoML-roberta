# Variante `inventario_stride_session_usage`

Esta variante lê o contexto em janelas de 384 pecinhas de texto, repetindo 128
pecinhas entre janelas. Durante a vida do processo, ela também acumula os
scores e os tokens de cada resposta.

## Fluxo

Cada chamada a `POST /answer` mantém a resposta usual e registra:

- `score` em `confidence_scores`;
- `input_tokens` em `input_tokens`.

O endpoint `POST /session-metrics` retorna estatísticas descritivas para os
scores e para os tokens por requisição, além do total acumulado de tokens.
O endpoint `POST /score-histogram` retorna um PNG com o histograma dos scores
acumulados.

```text
POST /answer
{"question": "Qual é o preço do Fone de ouvido Bluetooth?"}
```

```text
POST /session-metrics
```

```text
POST /score-histogram
```

As métricas vivem na memória da instância. Reiniciar o serviço zera o
acumulado.
