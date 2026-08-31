# Variante `inventario` — a que acerta, com o mesmo modelo

[← voltar ao README principal](../README.md)

Mesmo modelo da variante [`pdf/`](../pdf/README.md), resultado oposto: acerta,
em 2 a 4 segundos. A diferença não está no modelo. Está em **preparar o
contexto antes de entregá-lo**.

| | `pdf/` | aqui |
|---|---|---|
| modelo | `deepset/xlm-roberta-base-squad2` | **o mesmo** |
| contexto | 43 mil caracteres, 2 PDFs colados | 8.355 caracteres, 25 produtos |
| formato | texto cru, do jeito que saiu do PDF | frases curtas de português comum |
| tempo | 15 a 19 s | 2 a 4 s |
| acerta? | não | sim |

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `inventario.py` | **o coração da solução**: transforma o CSV em prosa |
| `service.py` | o serviço; carrega o CSV pelo `inventario.py` e responde |
| `context/estoque_marketplace.csv` | 25 produtos, 9 colunas, 7 categorias |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento — precisa incluir o `.py` **e** o `.csv` |

---

## A API

```
POST /answer
{"question": "Qual é o preço do Fone de ouvido Bluetooth?"}
```

Só a pergunta: o contexto é montado uma vez, quando o serviço sobe.

---

## O truque, que está em `inventario.py`

Modelos de QA extrativo foram treinados em texto corrido, não em tabelas.
Jogar as linhas cruas do CSV dentro do contexto dá respostas ruins, porque o
modelo não entende que a coluna `preco_brl` se refere ao produto que está três
colunas atrás.

Então cada linha do CSV vira quatro frases, e **cada frase repete o nome do
produto**:

```
O produto Fone de ouvido Bluetooth (SKU ELE-001) pertence à categoria
Eletrônicos e custa R$ 189,90. O estoque atual de Fone de ouvido Bluetooth é
de 42 unidades. O prazo de envio de Fone de ouvido Bluetooth é de 2 dias
úteis. O produto Fone de ouvido Bluetooth é vendido por Som & Cia, em
Recife-PE, com garantia de 12 meses.
```

A repetição parece boba, mas é ela que faz funcionar: quando o modelo fatia o
contexto, um pedaço pode acabar separado dos vizinhos. Com o nome do produto em
toda frase, o trecho continua encontrável sozinho.

Repare também que o código cuida do português: `189.90` vira `R$ 189,90`, e
`1 unidade` não vira `1 unidades`. Isso não é frescura — o modelo foi treinado
em texto escrito por gente, e responde melhor a texto que parece escrito por
gente.

Para ver o contexto gerado **sem carregar modelo nenhum** (roda em um segundo):

```bash
cd inventario && uv run --no-active python inventario.py
```

---

## Como rodar

```bash
just inventario serve      # terminal 1
just inventario curl-qa    # terminal 2: quatro perguntas seguidas
```

| Receita | O que faz |
|---|---|
| `just inventario curl-qa` | preço, estoque, prazo de envio e vendedor |
| `just inventario curl-nao-sei` | uma pergunta que o modelo **não** tem como responder |
| `just inventario run` | teste sem servidor, uma pergunta só |

---

## Saber dizer "não sei"

`just inventario curl-nao-sei` pergunta *"Qual é a capital da França?"*. Não há
nada sobre a França no estoque, e a resposta que volta é **vazia**.

Isso é um acerto, não uma falha. Vem do `handle_impossible_answer=True` em
`service.py`, que dá ao modelo permissão para não responder. Um sistema que
sempre devolve alguma coisa é mais perigoso do que um que admite não saber —
porque quem lê não tem como distinguir a resposta boa do chute.

---

## Experimentos

**Pergunte sobre um produto que existe, com outras palavras.** "Quanto custa o
fone bluetooth?" em vez de "Qual é o preço do Fone de ouvido Bluetooth?". Até
onde o modelo aguenta a variação?

**Estrague o contexto de propósito.** Em `inventario.py`, tire a repetição do
nome do produto das frases (deixe "O estoque atual é de 42 unidades."). Suba de
novo e repita `just inventario curl-qa`. É o experimento mais instrutivo da
pasta.

**Abra o CSV e procure o `CAS-002`.** O produto se chama `Panela de pressão
4,5 litros` — com uma vírgula **dentro** do nome. O arquivo resolve isso com
aspas, e o `inventario.py` lê com o módulo `csv` da biblioteca padrão, que
entende aspas. Se alguém tivesse escrito `linha.split(",")`, esse produto
sozinho quebraria o carregamento inteiro.
