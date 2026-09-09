# Variante `falcon90m` — LLM generativo minúsculo

[← voltar ao README principal](../README.md)

As outras pastas usam modelos de *question answering* extrativo (grifam um
trecho). Esta usa o **Falcon-H1-Tiny-90M-Instruct**: um LLM de ~91M parâmetros
que **escreve** a resposta. Ele cabe em CPU, baixa rápido e serve para
experimentar geração / instrução curta — não para fatos confiáveis.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | serviço BentoML com endpoint `/generate` |
| `justfile` | receitas (`serve`, `curl-generate`, ...) |
| `bentofile.yaml` | empacotamento (`just falcon90m build`) |

Não há pasta `context/`: não há contexto fixo; o prompt vai na requisição.

---

## A API

```
POST /generate
{
  "prompt": "Say hello in one short sentence.",
  "max_new_tokens": 64,
  "temperature": 0.0
}
```

Resposta típica:

```json
{
  "text": "Hey!",
  "model": "tiiuae/Falcon-H1-Tiny-90M-Instruct",
  "prompt_tokens": 12,
  "completion_tokens": 3,
  "max_new_tokens": 64,
  "temperature": 0.0
}
```

Modelo padrão: `tiiuae/Falcon-H1-Tiny-90M-Instruct` (inglês-first).

---

## Como rodar

Sem servidor:

```bash
just falcon90m run
```

Com servidor (duas janelas):

```bash
just falcon90m serve           # terminal 1
just falcon90m curl-generate   # terminal 2
```

Outras receitas:

| Receita | O que faz |
|---|---|
| `just falcon90m curl-generate-raw` | mesma geração, JSON cru |
| `just falcon90m curl-generate-file` | corpo lido de `tmp/payload.json` |
| `just falcon90m curl-format` | pedido de formatação em JSON |
| `just falcon90m swagger` | documentação interativa |
| `just falcon90m stop` | derruba o servidor |
| `just falcon90m build` | empacota num *bento* |

---

## Experimentos

**Troque o checkpoint.** No topo de `service.py` há alternativas comentadas
(`Coder`, `Tool-Calling`, `pre-DPO`). Compare formatação vs chat simples.

**Suba `temperature`.** Com `0.0` a saída é mais estável; com `0.7` varia mais
(e pode degradar em modelo tão pequeno).

**Peça fatos.** Pergunte algo factual em português e compare com `basico/`
(extrativo). A lição: 90M gera texto fluente, mas não é fonte de verdade.

**Compare o footprint.** Depois de `just falcon90m run`, note que o download é
muito menor que um RoBERTa QA típico em GB — o ponto desta variante é
*tamanho + latência*, não qualidade enciclopédica.
