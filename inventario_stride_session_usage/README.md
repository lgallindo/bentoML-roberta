# Variante `inventario_stride_session_usage` — o custo de muitas perguntas

[← voltar ao README principal](../README.md)

Terceiro e último degrau da série. A variante
[`inventario_stride_usage/`](../inventario_stride_usage/README.md) mede **uma**
pergunta e esquece. Esta guarda o que mediu e responde perguntas sobre o
conjunto: quanto já gastamos, e com que confiança o modelo vem respondendo.

| | o que acrescenta |
|---|---|
| [`inventario_stride/`](../inventario_stride/README.md) | escreve no código o tamanho da janela e a sobreposição |
| [`inventario_stride_usage/`](../inventario_stride_usage/README.md) | mede o custo de **uma** pergunta |
| **`inventario_stride_session_usage/`** ← você está aqui | acumula o custo de **muitas** perguntas |

---

## O que se espera deste programa

Três endpoints. O primeiro é o de sempre; os outros dois são novos:

| Endpoint | O que devolve |
|---|---|
| `POST /answer` | a resposta + o `token_usage` daquela chamada (igual à variante anterior) |
| `POST /session-metrics` | estatísticas de **todas** as chamadas até agora |
| `POST /score-histogram` | um PNG com a distribuição dos scores |

O serviço passa a ter **memória**. Cada `/answer` deixa dois rastros
guardados — o score e o total de tokens — e os dois endpoints novos apenas
olham para o que foi guardado.

---

## A palavra "sessão" aqui significa uma coisa bem específica

Não é sessão de usuário. Não é login. Não é cookie.

**Sessão = a vida do processo.** É o tempo entre o servidor subir e o servidor
morrer. Isso tem três consequências que valem mais do que o código:

1. **Reiniciar zera tudo.** Um `just … stop` seguido de `just … serve` e o
   acumulado volta a zero. Não há banco, não há arquivo, não há persistência.
2. **Cada réplica conta a sua.** Se o serviço subir com 3 réplicas para aguentar
   carga, existem 3 acumulados independentes, e cada `/session-metrics` responde
   só pela réplica que atendeu **aquela** chamada. Os números não somam, e pior:
   parecem certos.
3. **Portanto isto não é observabilidade de produção.** É um brinquedo honesto
   para ver o conceito funcionando. Em produção, esses números iriam para fora
   do processo — Prometheus, OpenTelemetry, um banco de séries temporais.

O terceiro ponto é o que mais aparece em prova e menos aparece em tutorial.
Métrica guardada dentro do processo que ela mede é métrica que some junto com
ele.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço; os acumuladores e os dois endpoints novos |
| `inventory.py` | converte o CSV em prosa (idêntico ao das pastas anteriores) |
| `context/estoque_marketplace.csv` | 25 produtos, 9 colunas |
| `justfile` | as receitas, incluindo `curl-metrics` e `curl-histogram` |
| `bentofile.yaml` | empacotamento: precisa de `matplotlib` e `pillow` além do resto |

---

## O código que importa

### 1. Os acumuladores são duas listas

```python
def __init__(self):
    ...
    self.confidence_scores = []
    self.input_tokens = []
```

Duas listas comuns, criadas quando o serviço sobe. É literalmente toda a
"memória" do sistema. Repare que elas são atributos **da instância**: é daí que
vem a consequência nº 2 lá de cima — outra réplica é outra instância, com outras
duas listas vazias.

### 2. `answer()` responde e anota

```python
result = self.pipeline(question=question, context=self.context)
token_usage = self._token_usage(question)
self.confidence_scores.append(result["score"])
self.input_tokens.append(token_usage["input_tokens"])
return {**result, "token_usage": token_usage}
```

Continua **uma única inferência** por pergunta. Anotar é `append` em lista, que
não custa nada perto de rodar o modelo.

### 3. `/session-metrics` só faz contas sobre o que já existe

```python
@bentoml.api(route="/session-metrics")
def session_metrics(self) -> dict:
    return {
        "request_count": len(self.confidence_scores),
        "cumulative_tokens": sum(self.input_tokens),
        "confidence_scores": self._descriptive_statistics(self.confidence_scores),
        "tokens": self._descriptive_statistics(self.input_tokens),
        ...
    }
```

O `route="/session-metrics"` existe porque, sem ele, o BentoML publicaria o
endpoint com o nome do método (`/session_metrics`, com underline). URL com
hífen é a convenção da web; nome de método com underline é a convenção do
Python. O argumento serve para as duas convenções conviverem.

### 4. A lista vazia é um caso de verdade, não um detalhe

```python
def _descriptive_statistics(self, values):
    if not values:
        return {"count": 0, "mean": None, "median": None,
                "min": None, "max": None, "stdev": None}
    ...
```

Sem essa guarda, subir o servidor e chamar `/session-metrics` **antes** da
primeira pergunta devolvia `HTTP 500 — An unexpected error has occurred`,
porque `mean([])` e `min([])` levantam exceção em Python.

E essa é exatamente a ordem em que uma pessoa curiosa mexe num serviço novo:
sobe, abre o Swagger, clica no endpoint que parece mais interessante. O caminho
"ainda não tem nada" não é um canto escuro do programa — é a **primeira** coisa
que alguém vê. Programa que trata bem o caso vazio devolve `count: 0` e diz a
verdade; programa que não trata devolve um erro 500 que não explica nada e faz
a pessoa achar que quebrou alguma coisa.

### 5. O endpoint que devolve imagem

```python
@bentoml.api(route="/score-histogram")
def score_histogram(self) -> Image.Image:
    figure, axis = plt.subplots()
    axis.hist(self.confidence_scores, bins=10, range=(0, 1))
    ...
    return Image.open(image_buffer)
```

Repare no tipo de retorno: `Image.Image`, do Pillow. Os outros endpoints
devolvem `dict` e viram JSON. Este devolve um objeto de imagem e o BentoML
resolve sozinho o resto — o `Content-Type: image/png`, os bytes no corpo, a
entrada certa no Swagger.

**A anotação de tipo não é enfeite: é ela que configura o endpoint.** É o mesmo
mecanismo que faz `question: str` virar um campo de texto no JSON de entrada.

O `range=(0, 1)` fixa o eixo X entre 0 e 1 mesmo quando há poucos dados, para
que dois histogramas tirados em momentos diferentes possam ser comparados. Sem
ele, o matplotlib ajustaria a escala a cada chamada e dois gráficos do mesmo
serviço pareceriam contar histórias diferentes.

---

## Como rodar

```bash
just inventario_stride_session_usage serve     # terminal 1
```

No terminal 2, o roteiro que faz a variante fazer sentido:

```bash
# 1. antes de qualquer pergunta -- repare no count: 0
just inventario_stride_session_usage curl-metrics

# 2. faça a mesma pergunta três ou quatro vezes
just inventario_stride_session_usage curl-qa
just inventario_stride_session_usage curl-qa
just inventario_stride_session_usage curl-qa

# 3. veja o acumulado crescer
just inventario_stride_session_usage curl-metrics

# 4. gere o gráfico e abra
just inventario_stride_session_usage curl-histogram
```

| Receita | O que faz |
|---|---|
| `just inventario_stride_session_usage run` | teste sem servidor: uma pergunta + as métricas |
| `just inventario_stride_session_usage curl-qa` | pergunta o preço do fone via HTTP |
| `just inventario_stride_session_usage curl-metrics` | as estatísticas acumuladas |
| `just inventario_stride_session_usage curl-histogram` | salva `score-histogram.png` nesta pasta |
| `just inventario_stride_session_usage swagger` | abre a documentação interativa |
| `just inventario_stride_session_usage stop` | derruba o servidor |

O `score-histogram.png` é ignorado pelo git (está no `.gitignore`): é resultado
de execução, não código.

---

## Lendo as métricas sem se enganar

```json
"confidence_scores": {"count": 3, "mean": 0.468, "stdev": 0.0},
"tokens": {"count": 3, "mean": 3410, "stdev": 0.0},
"cumulative_tokens": 10230
```

- **`stdev: 0.0`** com a mesma pergunta repetida está certo: a inferência é
  determinística, mesma entrada dá mesma saída. Desvio zero aqui é sinal de que
  o serviço está sadio, não de que a estatística quebrou.
- **`tokens.mean`** é o custo médio *por pergunta*; **`cumulative_tokens`** é o
  total desde que o servidor subiu. O primeiro serve para prever, o segundo para
  fechar a conta.
- **`confidence_scores` não é taxa de acerto.** O score é o quanto o modelo
  gostou do trecho que escolheu — nada mais. Ele pode estar 0,97 confiante numa
  resposta errada, e 0,46 confiante numa certíssima (é o caso aqui: `R$ 189,90`
  está correto e mesmo assim tirou 0,468). Confundir confiança com acerto é o
  erro mais comum de quem começa a medir modelo.

---

## Experimentos

**Faça perguntas diferentes e olhe o desvio.** Preço, estoque, prazo de envio,
vendedor, e uma que não tenha resposta ("Qual é a capital da França?"). Agora o
`stdev` dos scores para de ser zero, e o histograma ganha forma. Onde caiu a
pergunta impossível?

**Prove que a sessão morre.** Anote o `cumulative_tokens`, rode `stop`, suba de
novo e peça as métricas. Zero. Nenhum arquivo foi escrito, nenhum banco foi
consultado — e é exatamente por isso que isto não serviria para faturar
ninguém.

**Simule duas réplicas.** Suba o serviço duas vezes em portas diferentes:

```bash
just inventario_stride_session_usage serve                 # porta 3000
PORT=3001 just inventario_stride_session_usage serve       # porta 3001
```

Faça 5 perguntas na 3000 e 1 na 3001, e peça as métricas nas duas. São dois
mundos separados. Foi assim que você acabou de reproduzir, à mão, o motivo pelo
qual métricas de produção moram fora do processo.

**Quebre a guarda de propósito.** Tire o `if not values:` de
`_descriptive_statistics()`, suba e chame `/session-metrics` antes de qualquer
pergunta. Veja o 500 aparecer, e vá olhar o traceback no terminal do servidor.
Compare a mensagem que o cliente recebe (`An unexpected error has occurred`)
com a que o servidor tem (`StatisticsError: mean requires at least one data
point`). O cliente nunca fica sabendo o que houve — por isso o caso vazio é
responsabilidade de quem escreve o serviço.
