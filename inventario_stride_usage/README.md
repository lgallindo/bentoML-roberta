# Variante `inventario_stride_usage` — quanto custou esta pergunta

[← voltar ao README principal](../README.md)

Segundo degrau da série. A variante
[`inventario_stride/`](../inventario_stride/README.md) explicou que o contexto é
lido em janelas sobrepostas. Esta aqui **põe o número na tela**.

| | o que acrescenta |
|---|---|
| [`inventario_stride/`](../inventario_stride/README.md) | escreve no código o tamanho da janela e a sobreposição |
| **`inventario_stride_usage/`** ← você está aqui | mede o custo de **uma** pergunta |
| [`inventario_stride_session_usage/`](../inventario_stride_session_usage/README.md) | acumula o custo de **muitas** perguntas |

---

## O que se espera deste programa

O mesmo `POST /answer` de sempre, com a mesma resposta — mas o JSON que volta
ganha uma chave a mais, `token_usage`, contando quanto trabalho aquela pergunta
deu:

```json
{
  "score": 0.4680153004883323,
  "answer": " R$ 189,90.",
  "token_usage": {
    "question_tokens": 11,
    "context_tokens": 2251,
    "input_tokens": 3410,
    "window_count": 9,
    "window_sizes": [384, 384, 384, 384, 384, 384, 384, 384, 338],
    "max_seq_length": 384,
    "model_max_length": 512,
    "doc_stride": 128
  }
}
```

Por que isso importa: em qualquer serviço de LLM que você for pagar — OpenAI,
Anthropic, Google — a conta é feita **por token processado**, não por pergunta.
Um serviço que não sabe medir o próprio consumo é um serviço cuja fatura você
não sabe explicar.

---

## O número que surpreende

O contexto tem **2.251** pecinhas. O modelo processou **3.410**. Sobraram 1.159
pecinhas do nada — 51% a mais.

Não é bug. A conta fecha exatamente:

| parcela | pecinhas | de onde vem |
|---|---:|---|
| o contexto em si | 2.251 | os 25 produtos convertidos em prosa |
| a sobreposição | 1.024 | 8 emendas × 128 pecinhas repetidas |
| pergunta + marcadores | 135 | 9 janelas × (11 da pergunta + 4 marcadores) |
| **total** | **3.410** | confere com `input_tokens` |

Duas coisas que essa tabela ensina, e que não são óbvias:

1. **A sobreposição é repetição de verdade.** Aquelas 128 pecinhas de cada
   emenda passam pelo modelo duas vezes, e são cobradas duas vezes. O seguro
   contra perder uma resposta na borda custa 1.024 pecinhas por pergunta.
2. **A pergunta vai junto em toda janela.** O modelo precisa saber o que está
   sendo perguntado em cada pedaço que lê, então as 11 pecinhas da pergunta
   viajam 9 vezes. Perguntas longas custam caro em contexto grande — e o preço
   é multiplicado pelo número de janelas, não somado uma vez.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço; o `_token_usage()` é o assunto desta pasta |
| `inventory.py` | converte o CSV em prosa (idêntico ao da pasta anterior) |
| `context/estoque_marketplace.csv` | 25 produtos, 9 colunas |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento: os dois `.py` **e** o `.csv` |

---

## O código que importa

A medição está em `_token_usage()`, e o detalhe mais importante dela é o que
ela **não** faz:

```python
def _token_usage(self, question: str) -> dict:
    tokens = self.tokenizer(          # <-- o tokenizer, não o modelo
        question,
        self.context,
        truncation="only_second",     # se precisar cortar, corta o contexto,
                                      # nunca a pergunta
        max_length=MAX_SEQ_LENGTH,    # os mesmos 384 do pipeline
        stride=DOC_STRIDE,            # os mesmos 128 do pipeline
        return_overflowing_tokens=True,  # <-- devolve TODAS as janelas
    )
    window_sizes = [len(input_ids) for input_ids in tokens["input_ids"]]
```

**Ela não chama o modelo.** O *tokenizer* é só o tradutor que transforma texto
em números; ele é rápido e barato. O *modelo* é a parte cara, que pensa. Medir
com o tokenizer significa repetir apenas o recorte em janelas — não uma segunda
inferência.

Se a medição usasse o modelo de novo, cada pergunta custaria o dobro, e o
relatório de consumo seria a maior fonte de consumo do serviço. Ferramenta de
medição que altera o que está medindo não serve para medir.

O `return_overflowing_tokens=True` é o que faz o tokenizer devolver uma lista
de janelas em vez de um texto truncado. Sem ele, você receberia só a primeira
janela e concluiria — errado — que a pergunta custou 384 pecinhas.

E a junção com a resposta é uma linha só:

```python
result = self.pipeline(question=question, context=self.context)
return {**result, "token_usage": self._token_usage(question)}
```

O `{**result, ...}` copia tudo que o QA devolveu e acrescenta uma chave. Quem
já consumia esta API continua funcionando: nada foi renomeado nem removido.

---

## A API

```
POST /answer
{"question": "Qual é o preço do Fone de ouvido Bluetooth?"}
```

Não há endpoint separado de métricas — o consumo vem junto da resposta. Quem
quiser acumular números entre chamadas vai para a
[variante seguinte](../inventario_stride_session_usage/README.md).

---

## Como rodar

```bash
just inventario_stride_usage run          # sem servidor
```

```bash
just inventario_stride_usage serve        # terminal 1
just inventario_stride_usage curl-qa      # terminal 2
```

| Receita | O que faz |
|---|---|
| `just inventario_stride_usage run` | teste sem servidor, uma pergunta só |
| `just inventario_stride_usage curl-qa` | pergunta o preço do fone via HTTP |
| `just inventario_stride_usage swagger` | abre a documentação interativa |
| `just inventario_stride_usage stop` | derruba o servidor |
| `just inventario_stride_usage build` | empacota a variante num *bento* |

---

## Um aviso que aparece no terminal

Ao subir, o serviço imprime isto em vermelho:

```
Token indices sequence length is longer than the specified maximum sequence
length for this model (2251 > 512)
```

**Pode ignorar.** É o tokenizer avisando que 2.251 não cabe em 512 — o que já
sabemos, e é o motivo de existirem janelas. O aviso sai porque a linha que
calcula `context_tokens` tokeniza o contexto inteiro de uma vez só para contar,
sem recortar. Contar não é processar: esse texto nunca entra no modelo dessa
forma.

Vale saber distinguir os dois casos, porque a mensagem é a mesma: aqui é
inofensivo; num código que de fato mandasse essas 2.251 pecinhas para o modelo,
seria um erro grave.

---

## Experimentos

**Faça a pergunta mais longa que conseguir.** Algo como *"Considerando todo o
catálogo de produtos disponíveis nesta loja, qual seria o preço atualmente
praticado para o item Fone de ouvido Bluetooth?"*. Veja `question_tokens` subir
— e veja `input_tokens` subir **nove vezes mais**, porque a pergunta é repetida
em cada janela.

**Mexa no `DOC_STRIDE` e observe a conta.** Com `DOC_STRIDE = 0`, a parcela de
sobreposição some e `input_tokens` cai para perto de 2.251 + marcadores. Com
`DOC_STRIDE = 256`, o número de janelas quase dobra. Confira à mão com a tabela
da seção "O número que surpreende" — ela fecha em qualquer configuração.

**Confirme que medir é barato.** Cronometre `just inventario_stride_usage run` e
compare com `just inventario_stride run`, que não mede nada. A diferença é
pequena porque só o tokenizer roda a mais. Agora imagine o mesmo número se a
medição chamasse o modelo de novo.

**Pergunte algo que não está no estoque.** *"Qual é a capital da França?"* A
resposta vem vazia (graças ao `handle_impossible_answer=True`), mas o
`token_usage` vem cheio: as 9 janelas foram lidas do mesmo jeito. **Não saber a
resposta custa exatamente o mesmo que saber.** É um dos fatos mais
contra-intuitivos de servir modelos, e vale para os LLMs pagos também.
