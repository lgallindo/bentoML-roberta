# Variante `basico` — você entrega a pergunta *e* o texto

[← voltar ao README principal](../README.md)

A mais simples das três. A cada chamada você manda **duas** coisas: a pergunta
e o parágrafo onde a resposta deve ser procurada. Como você já escolheu o texto
certo, o modelo só precisa grifar o trecho — e acerta quase sempre, em menos de
um segundo.

É o ponto de partida. As outras duas variantes existem para mostrar o que
acontece quando o contexto **não** vem pronto de fora.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço inteiro — cerca de 15 linhas de código útil |
| `justfile` | as receitas desta variante (`serve`, `curl-qa`, ...) |
| `bentofile.yaml` | a receita de empacotamento, usada por `just basico build` |

Não há pasta `context/` aqui: o contexto viaja na requisição.

---

## A API

```
POST /answer
{"question": "Qual é a cor do céu?", "context": "O céu é geralmente azul ..."}
```

Modelo usado: `pierreguillou/bert-base-cased-squad-v1.1-portuguese`, um BERT
treinado em português.

---

## Como rodar

Sem servidor, num terminal só — a maneira mais rápida de saber se está tudo
funcionando:

```bash
just basico run
```

Com servidor, em **duas janelas de terminal**:

```bash
just basico serve      # terminal 1: deixe aberto, ele fica ocupado de propósito
just basico curl-qa    # terminal 2: faz a pergunta
```

Outras receitas desta pasta:

| Receita | O que faz |
|---|---|
| `just basico curl-qa-raw` | a mesma pergunta, sem `jq` — mostra o JSON cru |
| `just basico curl-qa-file` | manda o corpo da requisição a partir de um arquivo `.json` |
| `just basico swagger` | abre a documentação interativa no navegador |
| `just basico stop` | derruba o servidor |
| `just basico build` | empacota a variante num *bento* |

Veja todas com `just --list basico`.

---

## Experimentos

**Troque o modelo.** No topo de `service.py` há uma constante `MODEL_NAME` e
três sugestões comentadas. A mais instrutiva é `deepset/roberta-base-squad2`,
que só entende inglês: faça uma pergunta em português e veja o estrago. É a
demonstração mais barata de que escolher o modelo certo para o idioma importa.

**Mude o contexto e mantenha a pergunta.** Pergunte "Qual é a cor do céu?" com
um contexto que não fale de céu. Repare que o modelo devolve alguma coisa
assim mesmo — esta variante não usa `handle_impossible_answer`, então ela não
tem permissão para dizer "não sei". As outras duas têm.

**Aumente o contexto.** Cole três ou quatro parágrafos no campo `context` e
veja o tempo de resposta subir. É a variante `pdf/` acontecendo em miniatura.
