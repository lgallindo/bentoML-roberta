# Perguntas e respostas com BentoML

Três serviços web que respondem perguntas em português usando modelos de
*question answering* extrativo (o modelo não escreve a resposta: ele **grifa**
um trecho de um texto que você entregou).

As três variantes usam quase o mesmo código. O que muda entre elas é **de onde
vem o texto onde a resposta é procurada** — o chamado *contexto*. E é aí que
está a lição: duas variantes usam **exatamente o mesmo modelo**, mas uma acerta
em 3 segundos e a outra erra em 18.

---

## O que você vai precisar

| Ferramenta | Para quê | Como conferir |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | instala o Python e as bibliotecas | `uv --version` |
| [just](https://just.systems) ≥ 1.31 | roda os comandos deste projeto | `just --version` |
| `curl` e `jq` | fazem e formatam as chamadas à API | `curl -V` e `jq --version` |

Só Linux (ou WSL): duas receitas usam `ss` e `fuser` para cuidar das portas.

**Espaço em disco:** cerca de 5 GB de bibliotecas (`.venv/`) mais 1 a 2 GB de
modelos baixados na primeira execução. Não comece isso numa conexão ruim.

---

## Instalação

```bash
just sync
```

Isso cria a pasta `.venv/` com Python 3.13 e tudo que as três variantes usam.
Roda uma vez e serve para as três.

---

## Primeiro contato (um terminal só)

Antes de mexer com servidor, porta e HTTP, faça o teste mais simples possível:

```bash
just basico run
```

Isso carrega o modelo e faz **uma** pergunta, direto no terminal. Na primeira
vez demora alguns minutos, porque o modelo está sendo baixado. Se aparecer uma
resposta no fim, está tudo funcionando e você pode seguir.

---

## As três variantes

| pasta | o que você manda na requisição | tamanho do contexto | tempo por pergunta | resultado |
|---|---|---|---|---|
| `basico/` | a pergunta **e** o contexto | você escolhe (curtinho) | menos de 1 s | acerta |
| `pdf/` | só a pergunta | 43.069 caracteres (2 PDFs colados) | 15 a 19 s | **erra — de propósito** |
| `inventario/` | só a pergunta | 8.355 caracteres (25 produtos de um CSV) | 2 a 4 s | acerta |

Nas variantes `pdf/` e `inventario/` o contexto é carregado **uma vez**, quando
o serviço sobe, e fica guardado dentro dele. Por isso a requisição leva só a
pergunta.

Modelos usados:

- `basico/` → `pierreguillou/bert-base-cased-squad-v1.1-portuguese`
- `pdf/` e `inventario/` → `deepset/xlm-roberta-base-squad2` (**o mesmo nas duas**)

---

## Roteiro sugerido

Você vai precisar de **duas janelas de terminal**: numa o servidor fica de pé,
na outra você faz as perguntas.

### Terminal 1 — sobe o servidor

```bash
just basico serve
```

Espere aparecer a linha `Service QAService initialized`. Leva uns 15 segundos.
Deixe esse terminal aberto; ele fica "travado" de propósito.

### Terminal 2 — faz as perguntas

```bash
just basico curl-qa
```

Depois repita o par de terminais com as outras duas variantes, **nesta ordem**:

```bash
just pdf serve            # terminal 1
just pdf curl-falhas      # terminal 2  <- a demonstração do problema

just inventario serve     # terminal 1
just inventario curl-qa   # terminal 2  <- a solução
just inventario curl-nao-sei
```

Para derrubar o servidor: `Ctrl+C` no terminal 1, ou `just stop-all` de
qualquer lugar.

Cada variante também tem uma página de documentação interativa (Swagger UI) em
<http://127.0.0.1:3000/>, onde você pode testar a API pelo navegador, sem curl.

---

## O que cada variante ensina

### `basico/` — o caso fácil

Você entrega a pergunta e o parágrafo onde está a resposta. O modelo só precisa
grifar. Responde rápido e quase sempre acerta, porque **você** já fez o trabalho
difícil de escolher o texto certo.

### `pdf/` — o problema

O serviço cola dois documentos que não têm nada a ver um com o outro (o Decreto
do SAC e uma apostila do Sebrae) e manda os 43 mil caracteres para o modelo a
cada pergunta.

O modelo é míope: enxerga cerca de 384 "pedacinhos de palavra" por vez, mais ou
menos uma página. Para responder **uma** pergunta ele precisa arrastar essa
janelinha por ~100 pedaços e escolher o melhor grifo. Daí saem dois estragos:

- **Demora**: 15 a 19 segundos por pergunta.
- **Confusão**: perguntando *"Quantos dias tem o consumidor para cancelar o
  serviço?"*, a resposta que volta é `"DIA DAS CRIANÇAS E NATAL,"` — um trecho
  da apostila do Sebrae. E perguntando o prazo de resposta de uma reclamação,
  volta **vazio**, mesmo com "sete dias" escrito duas vezes no Decreto.

O modelo não está com defeito. Está faltando alguém **escolher a página certa
antes** de chamar o modelo. Esse passo que falta tem nome: é a etapa de **busca
(*retrieval*)** do RAG.

### `inventario/` — a solução

Mesmo modelo da variante anterior, resultado oposto. A diferença está no arquivo
`inventario/inventario.py`, que transforma cada linha do CSV em frases de
português comum, **repetindo o nome do produto em todas elas**:

> `O prazo de envio de Cafeteira elétrica é de 3 dias úteis.`

Como essa frase existe literalmente dentro do contexto, o modelo só precisa
grifá-la. Contexto 5 vezes menor e já organizado: 2 a 4 segundos, e acerta.

A receita `just inventario curl-nao-sei` mostra um detalhe importante:
perguntando *"Qual é a capital da França?"*, o serviço devolve resposta
**vazia** em vez de inventar. Um modelo que responde qualquer coisa é mais
perigoso do que um que admite não saber.

---

## A lição

> Trocar de modelo não foi o que resolveu. `pdf/` e `inventario/` rodam o mesmo
> `deepset/xlm-roberta-base-squad2`. O que resolveu foi **preparar o contexto**:
> deixá-lo pequeno, limpo e no formato que o modelo sabe ler.

---

## Comandos úteis

```bash
just                       # lista tudo
just --list inventario     # lista as receitas de uma variante

just ports                 # quais variantes estão de pé e em que portas
just stop-all              # derruba todas
just list                  # bentos já empacotados

just <variante> build      # empacota a variante num bento
just <variante> swagger    # abre a documentação interativa
```

Para rodar duas variantes ao mesmo tempo, mude a porta pelo ambiente:

```bash
just basico serve                  # fica na 3000
PORT=3001 just inventario serve    # vai para a 3001
```

---

## Quando algo dá errado

| Mensagem | O que fazer |
|---|---|
| `AVISO: a porta 3000 já está ocupada` | outra variante está de pé. `just stop-all`, ou suba esta em outra porta com `PORT=3001` |
| `ERRO: nada está respondendo em ...` | o servidor não está de pé. Volte ao terminal 1 e rode `just <variante> serve` |
| O terminal do `serve` parece travado | é assim mesmo. O servidor fica ocupando o terminal enquanto está de pé |
| A primeira execução demora muito | o modelo está sendo baixado (1 a 2 GB). Só acontece uma vez |
| `just pdf curl-falhas` deu respostas erradas | **é o esperado.** Essa variante existe para mostrar o problema |

---

## Onde olhar no código

| Arquivo | O que tem dentro |
|---|---|
| `basico/service.py` | o serviço mais simples, ~15 linhas de código útil |
| `pdf/service.py` | comentário longo no topo explicando por que esta variante erra |
| `inventario/inventario.py` | a conversão de CSV em prosa — o coração da solução |
| `comum.just` | os comandos compartilhados pelas três variantes |
| `*/bentofile.yaml` | a receita de empacotamento de cada variante |

Vale ler os comentários dos arquivos: eles explicam não só o que o código faz,
mas por que algumas decisões foram tomadas.
