# Variante `pdf_stride` — a sobreposição não conserta o contexto

[← voltar ao README principal](../README.md)

Mesma ideia da série
[`inventario_stride*`](../inventario_stride/README.md), aplicada ao contexto
ruim da variante [`pdf/`](../pdf/README.md): os dois PDFs colados, 43.071
caracteres, sem nenhum tratamento.

O resultado é a lição desta pasta. **Deixar as janelas explícitas não melhora
nada.** Melhora o que você enxerga — não a resposta.

---

## O que se espera deste programa

Responder perguntas sobre dois documentos: uma apostila do Sebrae sobre
atendimento e o Decreto 11.034/2022, que regula o SAC. A API é a de sempre:

```
POST /answer
{"question": "O que é o SAC?"}
```

E ele responde. Essa pergunta em particular sai certa:

```json
{"answer": " Serviço de Atendimento ao Consumidor", "score": 0.678}
```

O problema aparece nas perguntas que exigem achar um detalhe no meio dos
documentos — as mesmas que a variante `pdf/` erra.

---

## O que a sobreposição custa aqui

O contexto tem **9.750 pecinhas** de texto (*tokens*). Com janelas de 384 e 128
pecinhas repetidas em cada emenda, a conta fica assim:

| parcela | pecinhas | de onde vem |
|---|---:|---|
| o contexto em si | 9.750 | os dois PDFs, texto cru |
| a sobreposição | 4.992 | 39 emendas × 128 repetidas |
| pergunta + marcadores | 440 | 40 janelas × (7 + 4) |
| **total processado** | **15.182** | +56% sobre o contexto |

Compare com a variante
[`inventario_stride_usage/`](../inventario_stride_usage/README.md), que faz o
mesmo trabalho sobre um contexto bem preparado:

| | `inventario_stride*` | **`pdf_stride`** |
|---|---:|---:|
| caracteres de contexto | 8.355 | 43.071 |
| pecinhas de contexto | 2.251 | 9.750 |
| janelas | 9 | **40** |
| pecinhas processadas | 3.410 | **15.182** |
| acerta as perguntas difíceis? | sim | **não** |

**4,5 vezes mais caro, e pior.** Esse é o número que resume o repositório
inteiro.

---

## A prova: as duas perguntas que continuam falhando

A variante `pdf/` erra duas perguntas de propósito (veja
[`pdf/README.md`](../pdf/README.md)). Rodando exatamente as mesmas duas aqui,
com `doc_stride` declarado, as 40 janelas percorridas e as 15.182 pecinhas
processadas:

```
P: Qual é o prazo para resposta de reclamação no SAC?
R: ''   (score 0.5739)

P: Quantos dias tem o consumidor para cancelar o serviço?
R: ''   (score 0.5226)
```

Resposta **vazia** nas duas. O Decreto responde a primeira com todas as letras —
sete dias — e o modelo, mesmo tendo lido cada pedaço do texto com sobreposição
garantida, não achou.

### Por que a sobreposição não podia ajudar

Vale entender o que o `doc_stride` promete, porque ele cumpre a promessa:

> nenhuma resposta será perdida **por ter caído bem na emenda** entre duas
> janelas.

E é só isso. Ele garante que o texto foi **percorrido** por inteiro. Não tem
como garantir que o modelo vai **reconhecer** o trecho certo quando 40 janelas
disputam a mesma pergunta, e 39 delas falam de outra coisa.

Repare que a resposta vazia é, dentro do possível, o melhor comportamento
ruim: vem do `handle_impossible_answer=True`, que dá ao modelo permissão para
dizer "não sei" em vez de chutar. Um sistema que devolve vazio é irritante; um
que devolve um parágrafo aleatório da apostila do Sebrae com ar de certeza é
perigoso.

### O que faltou

Uma etapa de **busca** antes da leitura: escolher os dois ou três trechos que
têm chance de conter a resposta e mandar só eles para o modelo. É o que a
variante [`inventario/`](../inventario/README.md) faz na marra, preparando o
contexto na mão, e é o que os sistemas de RAG (*retrieval-augmented
generation*) fazem de forma automática.

`doc_stride` é sobre **como ler** um texto grande. O problema aqui é **o que
ler**. São perguntas diferentes, e nenhum ajuste de parâmetro responde a
segunda.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço; as constantes do topo e o `_load_pdf_context()` |
| `context/7121.pdf` | apostila do Sebrae sobre atendimento (31.762 caracteres) |
| `context/DECRETO_11034_2022.pdf` | o decreto do SAC (11.307 caracteres) |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento: o `.py` **e** os dois `.pdf` |

O carregamento dos PDFs é ingênuo de propósito:

```python
context_dir = Path(__file__).parent / "context"
pdf_files = sorted(context_dir.glob("*.pdf"))
self.context = "\n\n".join(
    self._load_pdf_context(pdf_file) for pdf_file in pdf_files
)
```

Todo PDF da pasta entra, em ordem alfabética, colado com duas quebras de linha.
Sem seleção, sem índice, sem busca. Jogar mais um PDF em `context/` aumenta o
contexto e piora o resultado, sem que uma linha de código mude.

---

## Como rodar

```bash
just pdf_stride run          # sem servidor, uma pergunta
```

```bash
just pdf_stride serve        # terminal 1
just pdf_stride curl-qa      # terminal 2 -- leva uns 15 segundos
```

| Receita | O que faz |
|---|---|
| `just pdf_stride run` | teste sem servidor, a pergunta que acerta |
| `just pdf_stride curl-qa` | "O que é o SAC?" via HTTP |
| `just pdf_stride swagger` | abre a documentação interativa |
| `just pdf_stride stop` | derruba o servidor |
| `just pdf_stride build` | empacota a variante num *bento* |

Paciência: cada pergunta leva de 15 a 19 segundos, porque são 40 janelas.

---

## Experimentos

**Rode as duas perguntas difíceis você mesmo.** Com o servidor de pé:

```bash
curl -sS -X POST -H 'Content-Type: application/json' \
  -d '{"question":"Qual é o prazo para resposta de reclamação no SAC?"}' \
  http://127.0.0.1:3000/answer | jq
```

A resposta esperada é *sete dias*, e está no Decreto duas vezes.

**Aumente a sobreposição até doer.** `DOC_STRIDE = 300` mais que dobra o número
de janelas e o tempo de resposta. As perguntas difíceis continuam falhando.
Gastar mais não é o mesmo que buscar melhor — e essa é uma lição que vale muito
além deste repositório.

**Tire um PDF da pasta.** Mova o `7121.pdf` (a apostila do Sebrae) para fora de
`context/` e suba de novo. O contexto cai para menos de um terço, e as
perguntas sobre o SAC passam a competir com muito menos ruído. Você acabou de
fazer, na mão e no braço, a etapa de busca que estava faltando.

**Compare o custo com o resultado.** Rode `just inventario_stride_usage curl-qa`
e olhe o `input_tokens`: 3.410 para uma resposta certa. Aqui são 15.182 para uma
resposta vazia. Em qualquer LLM pago, essa diferença é a fatura.
