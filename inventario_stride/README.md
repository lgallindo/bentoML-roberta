# Variante `inventario_stride` — o que o modelo faz quando o texto não cabe

[← voltar ao README principal](../README.md)

Primeiro degrau de uma série de três. As três usam o mesmo modelo e o mesmo CSV
da variante [`inventario/`](../inventario/README.md); o que muda é **o quanto
elas deixam você enxergar** do trabalho que o modelo faz por baixo.

| | o que acrescenta |
|---|---|
| **`inventario_stride/`** ← você está aqui | escreve no código o tamanho da janela e a sobreposição |
| [`inventario_stride_usage/`](../inventario_stride_usage/README.md) | mede o custo de **uma** pergunta |
| [`inventario_stride_session_usage/`](../inventario_stride_session_usage/README.md) | acumula o custo de **muitas** perguntas |

---

## O que se espera deste programa

Ele responde perguntas sobre um estoque de 25 produtos, exatamente como a
variante `inventario/`. A resposta é a mesma, o tempo é o mesmo, o score é o
mesmo.

Isso não é um defeito: **é a lição**. Esta pasta não muda o comportamento do
serviço, ela torna visível uma coisa que já estava acontecendo e que ninguém
tinha escrito em lugar nenhum.

---

## O problema: o modelo tem um limite de leitura

O `deepset/xlm-roberta-base-squad2` não consegue ler um texto de qualquer
tamanho. Ele lê no máximo **512 pecinhas de texto** (*tokens*) de uma vez —
esse é o `model_max_length` dele, um limite de fábrica.

O contexto do estoque tem **2.251 pecinhas**. Não cabe.

Então o `pipeline` do `transformers` faz o óbvio: corta o contexto em pedaços
que caibam, chamados **janelas**, e faz a mesma pergunta em cada janela. No
fim, escolhe a melhor das respostas encontradas.

### Por que as janelas se sobrepõem

Se os pedaços fossem cortados lado a lado, sem sobra, uma resposta que caísse
bem na emenda seria partida ao meio e perdida pelas duas janelas:

```
        ... vendido por Som & | Cia, em Recife-PE ...
                     janela 1 | janela 2
                              ^
                    a resposta "Som & Cia" morre aqui
```

Para evitar isso, cada janela nova **recomeça repetindo o final da anterior**.
Quantas pecinhas são repetidas é o que se chama `doc_stride`:

```
janela 1  [============================]
janela 2              [============================]
                      |<--128-->|
                       repetidas
```

Com 128 pecinhas de sobreposição, qualquer resposta com menos de 128 pecinhas
aparece inteira em pelo menos uma janela.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço; as duas constantes do topo são o assunto desta pasta |
| `inventory.py` | converte o CSV em prosa — mesmo trabalho do `inventario.py` da variante `inventario/` |
| `context/estoque_marketplace.csv` | 25 produtos, 9 colunas |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento: precisa incluir os dois `.py` **e** o `.csv` |

---

## O código que importa

Tudo se resume a três linhas no topo de `service.py`:

```python
MODEL_NAME = "deepset/xlm-roberta-base-squad2"
MAX_SEQ_LENGTH = 384    # tamanho de cada janela, em pecinhas
DOC_STRIDE = 128        # quantas pecinhas cada janela repete da anterior
```

e a dois argumentos entregues ao `pipeline`:

```python
self.pipeline = pipeline(
    "question-answering",
    model=self.model,
    tokenizer=self.tokenizer,
    handle_impossible_answer=True,
    max_seq_len=MAX_SEQ_LENGTH,   # <-- normalmente ficam implícitos
    doc_stride=DOC_STRIDE,        # <--
)
```

### A pegadinha: esses números já eram esses

Olhe o código do `transformers` que decide os valores quando ninguém os passa:

```python
if max_seq_len is None:
    max_seq_len = min(self.tokenizer.model_max_length, 384)
if doc_stride is None:
    doc_stride = min(max_seq_len // 2, 128)
```

Para este modelo, `model_max_length` é 512. Então o padrão é
`min(512, 384) = 384` e `min(192, 128) = 128` — **exatamente os números desta
pasta**.

Por isso a resposta aqui é idêntica, dígito por dígito, à da variante
`inventario/`:

```
inventario/          {'score': 0.4680153004883323, 'answer': ' R$ 189,90.'}
inventario_stride/   {'score': 0.4680153004883323, 'answer': ' R$ 189,90.'}
```

**Essa é a razão de ser desta pasta.** A variante `inventario/` já cortava o
contexto em 9 janelas com 128 pecinhas de sobreposição — só que em silêncio,
sem nada no código dizendo isso. Escrever os padrões à mão não muda o
resultado; muda o que você consegue ver, discutir e alterar.

Uma configuração que você não escreveu ainda é uma configuração. Ela só não é
sua.

---

## A API

```
POST /answer
{"question": "Qual é o preço do Fone de ouvido Bluetooth?"}
```

Só a pergunta: o contexto é montado uma vez, quando o serviço sobe.

---

## Como rodar

Sem servidor, a checagem mais rápida:

```bash
just inventario_stride run
```

Com servidor, em **duas janelas de terminal**:

```bash
just inventario_stride serve      # terminal 1: fica ocupado de propósito
just inventario_stride curl-qa    # terminal 2: faz a pergunta
```

| Receita | O que faz |
|---|---|
| `just inventario_stride run` | teste sem servidor, uma pergunta só |
| `just inventario_stride curl-qa` | pergunta o preço do fone via HTTP |
| `just inventario_stride swagger` | abre a documentação interativa |
| `just inventario_stride stop` | derruba o servidor |
| `just inventario_stride build` | empacota a variante num *bento* |

Veja todas com `just --list inventario_stride`.

---

## Experimentos

**Prove que os padrões são esses.** Comente as duas linhas `max_seq_len=` e
`doc_stride=` em `service.py`, suba de novo e repita a pergunta. O score tem
que continuar `0.4680153004883323`. Se mudou, você comentou outra coisa.

**Zere a sobreposição.** Ponha `DOC_STRIDE = 0`. As janelas passam a ser
cortadas lado a lado. Com o estoque, provavelmente nada muda — as respostas são
curtas e a chance de cair bem na emenda é pequena. Aumente `DOC_STRIDE` para
`300` e repare no efeito contrário: muito mais janelas, muito mais repetição,
mesma resposta. Sobreposição é um seguro, e como todo seguro tem um preço.

**Encolha a janela.** `MAX_SEQ_LENGTH = 128` obriga o modelo a ler o estoque em
pedacinhos. Repare que ele continua acertando o preço, porque cada frase do
contexto repete o nome do produto (o truque do
[`inventario/`](../inventario/README.md)). Agora `MAX_SEQ_LENGTH = 600`: passa
do limite de fábrica e o serviço quebra com

```
RuntimeError: The expanded size of the tensor (600) must match the existing
size (514) at non-singleton dimension 1.
```

Repare que o número que aparece é 514, não 512: este modelo guarda 514 posições
(as 512 úteis mais duas de controle). Vale ler o erro com calma — ele não diz
"você passou do limite", diz que dois tensores não têm o mesmo tamanho. Boa
parte dos erros de modelo chega assim, falando de tensores quando o problema é
de configuração.

**Quantas janelas são?** Esta pasta não te conta — é justamente o que a variante
[`inventario_stride_usage/`](../inventario_stride_usage/README.md) existe para
mostrar. Antes de ir lá, tente estimar: 2.251 pecinhas de contexto, janelas de
384, com 128 repetidas em cada emenda. Quantas janelas dão conta?
