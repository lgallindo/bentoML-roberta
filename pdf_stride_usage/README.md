# Variante `pdf_stride_usage` — o preço da má preparação, em número

[← voltar ao README principal](../README.md)

A variante [`pdf_stride/`](../pdf_stride/README.md) mostra que declarar as
janelas não conserta um contexto ruim. Esta aqui **põe a conta na resposta**,
do mesmo jeito que a
[`inventario_stride_usage/`](../inventario_stride_usage/README.md) faz com o
contexto bom.

Serve para uma coisa só, e ela é importante: transformar "o contexto está
ruim" — que é opinião — em um número que aparece em toda requisição.

---

## O que se espera deste programa

O mesmo `POST /answer` da variante `pdf_stride/`, com uma chave `token_usage`
a mais:

```json
{
  "answer": " Serviço de Atendimento ao Consumidor",
  "score": 0.6777365417219698,
  "token_usage": {
    "question_tokens": 7,
    "context_tokens": 9750,
    "input_tokens": 15182,
    "window_count": 40,
    "window_sizes": [384, 384, "... 37 vezes ...", 206],
    "max_seq_length": 384,
    "model_max_length": 512,
    "doc_stride": 128
  }
}
```

Quarenta janelas. Quinze mil pecinhas de texto processadas para responder uma
pergunta de sete.

---

## A comparação que justifica a pasta

Mesmo modelo, mesmo `max_seq_len`, mesmo `doc_stride`, mesma pergunta simples.
A única diferença é **como o contexto foi preparado**:

| | [`inventario_stride_usage/`](../inventario_stride_usage/README.md) | **`pdf_stride_usage/`** |
|---|---:|---:|
| origem do contexto | CSV virado prosa por `inventory.py` | dois PDFs colados, texto cru |
| caracteres | 8.355 | 43.071 |
| `context_tokens` | 2.251 | 9.750 |
| `window_count` | 9 | **40** |
| `input_tokens` | 3.410 | **15.182** |
| tempo por pergunta | 2 a 4 s | 15 a 19 s |
| perguntas difíceis | acerta | **devolve vazio** |

A conta fecha igual à das outras pastas, e pode ser conferida à mão:

| parcela | pecinhas |
|---|---:|
| contexto | 9.750 |
| sobreposição (39 emendas × 128) | 4.992 |
| pergunta + marcadores (40 × (7+4)) | 440 |
| **`input_tokens`** | **15.182** |

Repare que a parcela de sobreposição sozinha — 4.992 pecinhas — é **maior que o
contexto inteiro** da variante do inventário. Você paga, só em texto repetido,
mais do que a outra variante gasta no total.

---

## Por que medir isto muda a conversa

Sem número, a discussão sobre preparar contexto é estética: alguém acha que
ficou melhor, outro acha que não. Com `token_usage` na resposta, ela vira
engenharia — dá para comparar duas abordagens com a mesma régua.

E a régua é a mesma que os provedores de LLM usam para cobrar. Se estes PDFs
fossem para um modelo pago, cada pergunta custaria 15.182 tokens de entrada. A
mesma pergunta sobre o contexto arrumado custaria 3.410. **A diferença não está
no modelo nem no provedor: está no trabalho que alguém fez, ou não fez, antes
de mandar o texto.**

Vale notar o pior caso: quando a resposta vem **vazia**, os 15.182 tokens foram
processados assim mesmo. Não saber custa igual a saber — e aqui custa 4,5 vezes
mais do que custaria com o contexto preparado.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | igual ao da `pdf_stride/`, mais o método `_token_usage()` |
| `context/7121.pdf` | apostila do Sebrae (31.762 caracteres) |
| `context/DECRETO_11034_2022.pdf` | o decreto do SAC (11.307 caracteres) |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento: o `.py` **e** os dois `.pdf` |

O `_token_usage()` é o mesmo das outras variantes `_usage`: usa o **tokenizer**,
nunca o modelo, e por isso medir é barato. A explicação detalhada, com o papel
do `return_overflowing_tokens=True` e o porquê de não disparar uma segunda
inferência, está no
[README da `inventario_stride_usage/`](../inventario_stride_usage/README.md).

---

## Como rodar

```bash
just pdf_stride_usage run          # sem servidor
```

```bash
just pdf_stride_usage serve        # terminal 1
just pdf_stride_usage curl-qa      # terminal 2 -- uns 15 segundos
```

| Receita | O que faz |
|---|---|
| `just pdf_stride_usage run` | teste sem servidor, com o relatório de consumo |
| `just pdf_stride_usage curl-qa` | "O que é o SAC?" via HTTP, com `token_usage` |
| `just pdf_stride_usage swagger` | abre a documentação interativa |
| `just pdf_stride_usage stop` | derruba o servidor |
| `just pdf_stride_usage build` | empacota a variante num *bento* |

O aviso `Token indices sequence length is longer than...` que aparece em
vermelho é inofensivo aqui — a explicação está no
[README da `inventario_stride_usage/`](../inventario_stride_usage/README.md).

---

## Experimentos

**Meça uma pergunta que falha.** Pergunte *"Qual é o prazo para resposta de
reclamação no SAC?"*. A resposta vem vazia e o `input_tokens` vem 15.182 do
mesmo jeito. Escreva os dois números no quadro: é o argumento mais convincente
a favor de preparar contexto que este repositório tem.

**Tire um PDF e meça de novo.** Mova `7121.pdf` para fora de `context/`. Veja
`context_tokens` e `window_count` despencarem. Você reduziu o custo sem tocar
no modelo — só escolhendo melhor o que mandar.

**Calcule quanto custaria.** Pegue o preço por milhão de tokens de entrada de
qualquer LLM comercial e multiplique pelos 15.182 desta variante e pelos 3.410
da `inventario_stride_usage`. Agora multiplique por mil perguntas por dia. A
diferença entre as duas pastas é uma linha no orçamento.

**Compare as `window_sizes`.** Aqui são 39 janelas cheias (384) e uma de 206.
Na variante do inventário são 8 cheias e uma de 338. A última janela é sempre a
sobra — e o tamanho dela não significa nada sobre a qualidade da resposta.
