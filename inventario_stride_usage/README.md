# Variante `inventario_stride_usage`

Esta variante percorre o contexto em janelas de 384 pecinhas de texto, com
128 pecinhas repetidas entre janelas. Esse é o efeito de `doc_stride=128`.

O modelo faz a inferência uma vez. A mesma chamada `answer()` também conta as
pecinhas usadas nas janelas e devolve esses números em `token_usage`.

`window_count` é a quantidade de janelas, `window_sizes` é o tamanho de cada
uma e `input_tokens` é a soma desses tamanhos. A soma pode ser maior que o
tamanho do contexto porque as 128 pecinhas repetidas contam novamente.

```text
POST /answer
{"question": "Qual é o preço do Fone de ouvido Bluetooth?"}
```

A resposta contém `answer`, `score`, `start`, `end` e os dados de consumo. Não
há endpoint separado de métricas nesta variante.
