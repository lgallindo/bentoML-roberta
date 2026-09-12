# Variante `pdf_rag` — a busca que faltava

[← voltar ao README principal](../README.md)

Mesmos dois PDFs da variante [`pdf/`](../pdf/README.md). Mesmo modelo
(`deepset/xlm-roberta-base-squad2`). Mesma máquina, mesma CPU, nenhum ajuste
fino, nenhuma biblioteca nova.

A única diferença é que, **antes** de chamar o modelo, alguém escolhe quais
pedaços do texto valem a pena ler.

O comentário no topo de `pdf/service.py` termina prometendo esta pasta:

> **O QUE ESTÁ FALTANDO:** alguém precisa ESCOLHER o pedaço certo do texto
> ANTES de chamar o modelo (…) Esse passo que falta tem nome: é a "busca"
> (*retrieval*) do RAG.

Aqui está o passo que faltava.

---

## O antes e o depois

| | `pdf/` | `pdf_rag/` (esta pasta) |
|---|---|---|
| contexto enviado ao modelo | 43.069 letras, os 2 PDFs colados | ~245 letras por vez, 6 trechos |
| chamadas ao modelo por pergunta | ~100 janelas deslizantes | 6 |
| tempo por pergunta | 15 a 19 s | 0,5 a 0,9 s |
| "Qual é o prazo para resposta de reclamação no SAC?" | `""` (vazio) | **"sete dias corridos"** |
| diz de onde tirou a resposta | não | sim — documento e página |
| dependências novas | — | **nenhuma** |

O ponto que vale mais que a tabela: **o modelo nunca esteve com defeito.**
Ele respondeu certo o tempo todo, desde que a pergunta viesse acompanhada do
texto certo. Quem estava com defeito era o contexto.

---

## Como funciona, em três passos

Tudo mora em `busca.py`, que não importa nada além da biblioteca padrão do
Python e do `pypdf` (que a variante `pdf/` já usava).

**1. Quebrar.** Os PDFs viram 173 trechos de ~245 letras cada.

**2. Indexar.** Contamos quais palavras aparecem em quais trechos. Acontece
uma vez, quando o serviço sobe: 0,6 segundo.

**3. Buscar.** Cada trecho ganha uma nota **BM25** — contagem de palavras com
duas correções de bom senso (saturação e tamanho, explicadas no código). Os
6 melhores vão para o modelo.

Não há banco de vetores. Não há *embeddings*. Não há `pip install` nenhum. A
busca inteira leva **0,15 milissegundo** — ou seja, a etapa que consertou a
variante custa ~4.000 vezes menos que a chamada ao modelo que ela conserta.

---

## Duas decisões que decidiram tudo

Estas duas não são detalhe de implementação: são a variante inteira. As duas
foram descobertas medindo, depois de versões que não funcionaram.

### 1. Cortar o texto em cima da estrutura que ele já tem

Três jeitos de quebrar o mesmo texto foram medidos, com o mesmo modelo e as
mesmas perguntas:

| corte | resultado |
|---|---|
| pedaços de 700 letras, em parágrafo | o trecho certo vinha, mas com outro prazo ("noventa dias") colado junto — e o modelo grifava o **prazo errado** |
| pedaços de 400 letras, na marra | o corte caía no meio da frase e **todas** as perguntas viraram resposta vazia |
| **um trecho por artigo, cortado em fim de frase** | **funcionou** |

Num documento jurídico a unidade de sentido é o **artigo**, não o parágrafo
visual nem um número redondo de letras. O Decreto já vem dividido em `Art. 1º`,
`Art. 2º`… — cortar ali é cortar onde o próprio documento diz que uma ideia
terminou.

### 2. Um pipeline por trecho, em vez de colar os trechos

A primeira versão colava os 6 melhores trechos num contexto só e fazia **uma**
chamada. Não funcionou. Com `handle_impossible_answer=True`, quanto maior o
contexto, mais a resposta vazia ganha dos grifos de verdade. Medido no mesmo
trecho do Art. 13:

```
600 letras de contexto -> "sete dias corridos"   (score 0,32)
768 letras de contexto -> ""                     (o vazio ganha, com 0,42)
```

Então o modelo é chamado **uma vez por trecho**, e no fim comparamos os grifos.
Cada chamada enxerga um texto curto, onde a resposta vazia não tem vantagem
artificial.

É a mesma ideia da série [`*_stride`](../pdf_stride/README.md), com a
diferença que é o ponto todo: lá as ~100 janelas passeiam pelo documento
**inteiro**; aqui as 6 chamadas só olham o que a busca já escolheu.

---

## O vazio que é a resposta certa

Esta é a pergunta que a variante `pdf/` erra de forma mais escandalosa:

> **"Quantos dias tem o consumidor para cancelar o serviço?"**
>
> `pdf/` → `"DIA DAS CRIANÇAS E NATAL,"` — um trecho da apostila do Sebrae
> `pdf_rag/` → `""` (vazio)

O vazio aqui **é a resposta certa**, e vale parar nele.

O Decreto não dá prazo nenhum para cancelamento. O Art. 14 manda fazer o
"processamento **imediato** do pedido de cancelamento". Não existem "quantos
dias" — a pergunta pressupõe um prazo que o documento não tem.

E as duas variantes reagem de formas opostas: a `pdf/` vai buscar uma resposta
qualquer num texto sobre outro assunto, e esta admite que não sabe. Um sistema
que sempre responde alguma coisa é mais perigoso que um que sabe dizer "não
está aqui" — é o mesmo argumento do `handle_impossible_answer` da variante
[`inventario/`](../inventario/README.md), agora valendo para o documento
inteiro.

---

## O campo `fonte`, e por que ele não é enfeite

Toda resposta vem com a página de onde saiu:

```json
{
  "answer": "sete dias corridos,",
  "score": 0.4721,
  "fonte": {"documento": "DECRETO_11034_2022.pdf", "pagina": 3, "nota_busca": 3.991},
  "trechos_lidos": 6,
  "busca_ms": 0.15,
  "modelo_ms": 622.4
}
```

Você pode abrir o PDF na página 3 e conferir. Um sistema de RAG que não sabe
dizer de onde tirou a resposta não pode ser auditado — e, em produção, não
poder auditar costuma ser um problema maior do que errar de vez em quando.

---

## O que esta variante **não** resolve

A busca é por **palavra**. Se a pergunta usa uma palavra e o documento usa
outra para a mesma coisa, o BM25 não faz a ponte. E o caso está vivo aqui
dentro:

> a pergunta diz "**resposta** de reclamação"
> o Art. 13 diz "as demandas serão **respondidas**"

Para o BM25 essas são duas palavras diferentes. O resultado é que **o trecho
certo cai para a sexta posição** do ranking. Só funciona porque pegamos os 6
primeiros — não o primeiro.

Prove você mesmo:

```bash
PORT=3000 just pdf_rag curl-limite
```

Com `trechos=6`, sai "sete dias corridos". Com `trechos=3`, a mesma pergunta,
o mesmo modelo e o mesmo documento devolvem vazio. A resposta certa estava a
três posições de distância de nunca ser encontrada.

Fechar esse buraco é o trabalho dos *embeddings*: representar "resposta" e
"respondidas" como pontos vizinhos, em vez de palavras diferentes. É o assunto
da próxima variante.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `busca.py` | **o coração**: quebra, indexa e busca. Sem dependência nova |
| `service.py` | o serviço: `/answer` e `/search` |
| `context/*.pdf` | os mesmos dois PDFs da variante `pdf/` |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento |

---

## Como rodar

```bash
just pdf_rag busca          # só a busca, sem servidor e sem modelo (instantâneo)
just pdf_rag run            # as 4 perguntas, sem servidor
just pdf_rag serve          # sobe na 3000
```

Com o servidor de pé, em outro terminal:

| Receita | O que faz |
|---|---|
| `just pdf_rag curl-qa` | a pergunta que a `pdf/` não responde |
| `just pdf_rag curl-comparar` | as duas perguntas da `just pdf curl-falhas`, aqui |
| `just pdf_rag curl-search` | só os trechos que a busca entrega, com as notas |
| `just pdf_rag curl-limite` | o buraco do BM25, com `trechos=6` vs `trechos=3` |

---

## Experimentos

**Veja a busca sem o modelo.** Rode `just pdf_rag busca`. É instantâneo,
porque não tem rede neural nenhuma ali — é contagem de palavras. Compare com
os 15 a 19 segundos de uma única pergunta na variante `pdf/`.

**Descubra de quem é a culpa.** Quando uma resposta vier ruim, chame `/search`
com a mesma pergunta. Se o trecho certo **não** aparece na lista, o problema é
da busca. Se aparece e o modelo errou mesmo assim, o problema é do modelo. São
dois consertos diferentes, e confundir os dois custa dias.

**Quebre a quebra.** Em `busca.py`, mude `TAMANHO_ALVO` de 300 para 700 e rode
de novo. Veja a resposta do prazo virar "noventa dias" — o prazo errado, do
mesmo artigo. Depois tente 100: os trechos ficam curtos demais para conterem
a resposta inteira.

**Ache uma pergunta que o BM25 não alcança.** Escreva uma pergunta sobre o
Decreto usando só sinônimos das palavras que ele usa. Confira com `/search`
que o trecho certo não aparece. Essa é a lista de casos que a próxima variante
precisa consertar.
