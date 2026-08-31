# Variante `pdf` — a que erra de propósito

[← voltar ao README principal](../README.md)

> **Leia isto antes de rodar:** esta variante **responde errado**, e isso é
> intencional. Ela não está quebrada e você não instalou nada torto. Ela existe
> para você ver o problema acontecer com os próprios olhos.

O serviço cola dois documentos que não têm nada a ver um com o outro e manda os
~43 mil caracteres inteiros para o modelo a cada pergunta. O resultado é lento
e errado.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço, com um comentário longo no topo explicando a falha |
| `context/7121.pdf` | apostila do Sebrae, 32 páginas, 31.762 caracteres |
| `context/DECRETO_11034_2022.pdf` | o Decreto do SAC, 5 páginas, 11.307 caracteres |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento — repare que ele precisa incluir `context/*.pdf` |

Os dois PDFs são lidos **uma vez**, quando o serviço sobe, e colados num texto
só. Em ordem alfabética, então a apostila do Sebrae vem primeiro e o Decreto
fica na segunda metade.

---

## A API

```
POST /answer
{"question": "O que é o SAC?"}
```

Só a pergunta. O contexto já está dentro do serviço, então mandar um campo
`context` não faria sentido — o servidor ignoraria.

Modelo: `deepset/xlm-roberta-base-squad2` — **o mesmo** da variante
`inventario/`, que acerta. Guarde essa informação.

---

## Como rodar

```bash
just pdf serve          # terminal 1
just pdf curl-falhas    # terminal 2  <- a demonstração
```

| Receita | O que faz |
|---|---|
| `just pdf curl-qa` | uma pergunta que ela **acerta**, meio por sorte (15 a 19 s) |
| `just pdf curl-falhas` | as duas perguntas que ela **erra** — é o ponto da variante |
| `just pdf run` | teste sem servidor (paciência: modelo + 15 a 19 s) |

Tenha paciência: **cada pergunta leva de 15 a 19 segundos.**

---

## Por que ela erra

O modelo é míope. Ele enxerga cerca de 384 "pedacinhos de palavra" por vez,
mais ou menos uma página. Para responder **uma** pergunta sobre um texto de 43
mil caracteres, ele precisa arrastar essa janelinha por volta de 100 vezes,
grifar o melhor candidato dentro de cada pedaço e escolher o grifo de maior
nota no fim. Daí saem os dois estragos:

**1. Demora.** São ~100 leituras por pergunta, na CPU.

**2. Confusão.** Um pedaço qualquer da apostila pode tirar nota maior do que a
resposta certa, que está lá no Decreto:

| Pergunta | Resposta certa | O que volta |
|---|---|---|
| "Qual é o prazo para resposta de reclamação no SAC?" | sete dias (está escrito **duas vezes** no Decreto) | `""` — vazio |
| "Quantos dias tem o consumidor para cancelar o serviço?" | está no Decreto | `"DIA DAS CRIANÇAS E NATAL,"` — trecho da apostila |
| "O que é o SAC?" | está no começo do Decreto | acerta, num pedaço sem concorrência |

---

## O que está faltando

Alguém precisa **escolher o pedaço certo do texto antes** de chamar o modelo:
procurar a página que fala do assunto perguntado e mandar só aquela página.

Esse passo que falta tem nome. É a etapa de **busca** (*retrieval*) do RAG,
*Retrieval-Augmented Generation*.

Repare que a solução **não** é trocar de modelo. A variante
[`inventario/`](../inventario/README.md) roda exatamente o mesmo
`deepset/xlm-roberta-base-squad2` e acerta em 2 a 4 segundos, porque lá o
contexto chega pequeno e arrumado.

---

## Experimentos

**Tire um PDF.** Mova `7121.pdf` para fora de `context/`, suba de novo e repita
`just pdf curl-falhas`. Com só o Decreto, o contexto cai para 11 mil
caracteres. Fica mais rápido? Passa a acertar?

**Meça.** Ponha `time` na frente do curl e confirme os 15 a 19 segundos. Depois
compare com `just inventario curl-qa`.
