# Variante `api` — o contexto vem de fora

[← voltar ao README principal](../README.md)

As outras variantes leem o contexto de um arquivo que já está no disco. Esta
busca o contexto numa **API externa** quando o serviço sobe:
[BrasilAPI](https://brasilapi.com.br), aberta, sem chave, sem cadastro.

O assunto são os **feriados nacionais**. A pergunta é do tipo *"Quando é o
Carnaval?"*.

## Rodar

```
just api contexto      # monta e imprime o contexto, sem modelo e sem servidor
just api serve         # sobe o servidor (outro terminal)
just api curl-qa       # quatro perguntas
```

O ano vem da variável de ambiente, antes do `just`:

```
FERIADOS_ANO=2027 just api serve
```

## As três coisas que esta variante ensina

**1. O contexto pode mudar sem o código mudar.** Suba com 2026, pergunte
*"Quando é o Carnaval?"*, suba com 2027, pergunte de novo. Mesmo código, mesmo
modelo, mesma pergunta, resposta diferente. `just api curl-mudou` faz o roteiro.

**2. A dependência externa pode cair.** `api.py` grava um cache em `context/` a
cada busca bem-sucedida e cai nele quando a rede falha. O serviço sobe assim
mesmo e **diz de onde veio o contexto** — o campo `origem` vem em toda resposta.
Um serviço que morre porque um terceiro caiu é frágil; um que finge que está
tudo bem é pior.

> A BrasilAPI responde **403** para o `User-Agent` padrão do `urllib`. Não é bug
> nosso: é a API recusando cliente que não se identifica. Ver `CABECALHOS` em
> [`api.py`](api.py).

**3. A redação do contexto decide a resposta.** Isto foi medido, não adivinhado.
Com 5 feriados, duas redações diferentes empatavam. Com os 14 de verdade:

| Redação | Acertos |
| --- | --- |
| `O feriado X acontece em D. O feriado X cai numa W. A data D é feriado por causa de X.` | **4/7** |
| `O feriado X é comemorado no dia D. No dia D comemora-se o feriado X. O feriado X cai em um dia da semana que é W.` | **6/7** |

Mesmo modelo, mesmo tamanho de contexto, mesmas perguntas. O que mudou foi a
ordem das frases e a expressão literal *"dia da semana"*, que é a que a pergunta
usa. É a lição da variante [`pdf/`](../pdf/README.md), uma volta mais fina: não é
só o **tamanho** do contexto que decide, é a **redação**.

## A sétima pergunta

`just api curl-tipo-errado`

```
"Quando é o feriado de Tiradentes?"  ->  "terça-feira"   (score 0,52)
```

Perguntamos **quando** e o modelo respondeu um **dia da semana**. Resposta do
tipo errado. E ele não está mentindo: Tiradentes de fato cai numa terça.

Agora compare com as respostas **certas** de `just api curl-qa`, medidas no
mesmo servidor em 09/09/2026:

| Pergunta | Resposta | Score |
| --- | --- | --- |
| Quando é o Carnaval? | 16 de fevereiro de 2026 ✅ | **0,08** |
| Quando é o Natal? | 25 de dezembro de 2026 ✅ | **0,06** |
| Em que dia da semana cai o Natal? | sexta-feira ✅ | 0,61 |
| Qual feriado acontece em 7 de setembro? | Independência do Brasil ✅ | 0,19 |
| Qual é a capital da França? | *(vazio)* ✅ | 0,96 |
| **Quando é o feriado de Tiradentes?** | **terça-feira** ❌ | **0,52** |

A resposta errada tem score maior que quatro das cinco certas. **Confiança alta
não é sinal de resposta certa.** Um limiar do tipo *"rejeite abaixo de 0,3"*
teria descartado as duas datas corretas e mantido o erro.

Nenhuma dessas sete chamadas gerou erro de HTTP. Do ponto de vista do servidor,
o serviço passou o dia inteiro saudável.

É exatamente para isso que serve a variante
[`inventario_stride_session_usage/`](../inventario_stride_session_usage/README.md):
olhar a **distribuição** dos scores ao longo da sessão, em vez de um score
isolado por resposta.
