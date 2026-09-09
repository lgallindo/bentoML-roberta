# Variante `falcon90m_apps` — quatro apps, e uma lição sobre suíte verde

[← voltar ao README principal](../README.md)

Quatro aplicativos mínimos sobre o mesmo Falcon-H1-Tiny-90M da variante
[`falcon90m/`](../falcon90m/README.md): extrair JSON, rotear intenção,
preencher template e etiquetar e-mail. São as tarefas em que um modelo de 90M
tem alguma chance — texto curto, saída curta, resposta de uma palavra.

A suíte passa 22 de 22. **E é justamente por isso que esta pasta é a mais
instrutiva do repositório.**

---

## O que se espera deste programa

Quatro endpoints, todos devolvendo JSON:

| Endpoint | Corpo | O que faz |
|---|---|---|
| `POST /extract_json` | `text`, `keys[]` | acha campos no texto e devolve JSON |
| `POST /route_intent` | `text`, `labels?` | classifica em BILLING / TECH / CANCEL / OTHER |
| `POST /fill_template` | `template`, `data{}` | troca `{placeholders}` pelos valores |
| `POST /tag_email` | `subject`, `tags?` | etiqueta em meeting / invoice / spam / support |

Rode a suíte offline, sem servidor nem porta:

```bash
just falcon90m_apps test
```

```
22 passed, 0 failed, 22 total
```

---

## Agora leia a coluna `raw`

`raw` é **o que o modelo respondeu, antes de qualquer tratamento**. A suíte
imprime os dois. Compare:

| caso | o modelo disse (`raw`) | o serviço devolveu | quem acertou |
|---|---|---|---|
| `billing_double_charge` | `TECH` | `BILLING` | a regra |
| `tech_wifi` | `dropped` | `TECH` | a regra |
| `billing_refund` | `Bill` | `BILLING` | a regra |
| `other_weather` | `Rain` | `OTHER` | o fallback |
| `spam_subject` | `Support` | `spam` | a regra |
| `invoice_receipt` | `Support` | `invoice` | a regra |
| `meeting_invite` | `Calendar invite: design review` | `meeting` | a regra |

Nos sete casos de roteamento, o modelo acertou **um** sozinho (`cancel_sub`).
Nos seis de e-mail, também **um** (`invoice_subject`). Em `billing_double_charge`
ele não só errou como errou com confiança, respondendo `TECH` para uma
reclamação de cobrança dupla.

E o melhor caso está no preenchimento de template:

```
template: "Hello {name}, your order {id} ships on {date}."
data:     {"name": "Maya", "id": "A-17", "date": "Friday"}

o modelo: "Hello, Maya, your order, 17A-Friday, ships on Friday."
o Python: "Hello Maya, your order A-17 ships on Friday."
```

O modelo embaralhou `A-17` em `17A-Friday`. Quem acertou foi um
`str.replace()` de três linhas. Nos quatro casos de template, `used_model` sai
`false`: **a LLM nunca ganhou**.

---

## A lição

> Uma suíte verde não diz que o modelo funciona. Diz que o **sistema**
> funciona.

O sistema aqui é o modelo **mais** um punhado de regras baratas em
`engine.py`:

```python
if heuristic:          # palavra-chave no texto: "refund", "cancel", "wifi"...
    label = heuristic  # a regra ganha SEMPRE que dispara
elif model_label:      # senão, o que o modelo disse (se casar com a lista)
    label = model_label
elif "OTHER" in labels_u:
    label = "OTHER"    # senão, o balde do resto
```

E, na extração, expressões regulares que passam na frente do modelo:

```python
# _enrich_from_text: "Prefer cheap high-precision patterns over tiny-model slips."
m = re.search(r"\b([A-Z][a-z]+)\s+lives\s+in\s+([A-Z][a-zA-Z]+)\b", text)
```

Foi essa regex que consertou `{"name": "Recife"}` para `{"name": "Alice"}`.

Nada disso é trapaça — é engenharia honesta, e é assim que se põe modelo
pequeno em produção. O problema seria **não saber**: olhar `22 passed`,
concluir "o Falcon 90M resolve roteamento de intenção" e levar isso para um
sistema real onde as palavras-chave não cobrem os casos.

Três hábitos que esta pasta ensina:

1. **Meça o modelo separado do sistema.** Os campos `raw`, `model_label`,
   `heuristic` e `used_model` existem para isso. Um serviço que só devolve a
   resposta final não permite saber quem acertou.
2. **Desconfie de agregado.** "22 de 22" é verdade e é enganoso ao mesmo tempo.
3. **Considere não usar o modelo.** Em `fill_template`, a resposta certa era
   `str.replace`. Saber quando *não* chamar a LLM é metade do trabalho.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `engine.py` | os quatro apps, as regras e os *parsers* — o código que interessa |
| `service.py` | só a casca BentoML: quatro `@bentoml.api` chamando o engine |
| `suite.py` | os 22 casos de teste, rodam sem servidor |
| `justfile` | as receitas, incluindo `test` e `test-http` |
| `bentofile.yaml` | empacotamento: os três `.py` |

A separação entre `engine.py` e `service.py` é deliberada: a lógica não depende
do BentoML, então `just falcon90m_apps test` exercita tudo sem subir servidor,
sem abrir porta e sem HTTP. Teste que precisa de servidor de pé é teste que
ninguém roda.

Repare também no `_parse_json_object()`: o modelo às vezes devolve o JSON
embrulhado em ```` ```json ````, às vezes cru, às vezes com texto em volta. O
parser tenta os três. **Saída de LLM é texto, não estrutura** — quem trata como
estrutura quebra na terceira requisição.

---

## Como rodar

Offline, o caminho normal:

```bash
just falcon90m_apps test           # 22 casos, sem servidor
just falcon90m_apps test-verbose   # o mesmo, mostrando cada prompt
```

Por HTTP, na porta 8080 (deixa as 3xxx livres para as outras variantes):

```bash
just falcon90m_apps test-http      # sobe, roda os 4 curls, derruba sozinho
```

Ou na mão, em dois terminais:

```bash
just falcon90m_apps serve-open              # terminal 1 (porta 8080)
PORT=8080 just falcon90m_apps curl-all      # terminal 2
```

| Receita | O que faz |
|---|---|
| `just falcon90m_apps test` | a suíte offline inteira |
| `just falcon90m_apps test-http` | sobe → `curl-all` → derruba, tudo sozinho |
| `just falcon90m_apps serve-open` | sobe na 8080 (fora da faixa 3xxx) |
| `PORT=8080 just falcon90m_apps curl-extract-json` | só a extração de JSON |
| `PORT=8080 just falcon90m_apps curl-route-intent` | só o roteamento |
| `PORT=8080 just falcon90m_apps curl-fill-template` | só o template |
| `PORT=8080 just falcon90m_apps curl-tag-email` | só a etiqueta de e-mail |

---

## Experimentos

**Desligue as regras e veja a suíte desabar.** Em `engine.py`, faça
`_heuristic_intent()` e `_heuristic_email_tag()` devolverem `None` sempre. Rode
`just falcon90m_apps test`. Quantos dos 22 sobram? Esse é o número que mede o
**modelo** — o outro media o sistema.

**Escreva um caso que as regras não cobrem.** As palavras-chave de BILLING são
`invoice, charged, refund, bill, payment, receipt`. Mande *"You took money from
my card twice"* — nenhuma dispara, e a decisão volta para o modelo. Acertou?

**Troque os rótulos.** `route_intent` aceita `labels` na requisição. Peça
`["URGENTE", "NORMAL"]`, que as regras não conhecem. Sem heurística possível, é
o modelo puro decidindo.

**Rode a mesma coisa no Gemma.** Troque `MODEL_NAME` em `engine.py` para
`google/gemma-3-270m-it` e rode a suíte. Três vezes mais parâmetros melhoram a
coluna `raw`? Vale a memória a mais?

**Meça o custo do template.** Cronometre `curl-fill-template` e compare com o
tempo de um `str.replace` em Python. Você acabou de medir o preço de usar uma
LLM para uma tarefa que não precisava de uma.
