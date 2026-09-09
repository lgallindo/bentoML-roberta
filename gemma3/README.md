# Variante `gemma3` — Gemma 3 270M Instruct

[← voltar ao README principal](../README.md)

Irmã da [`falcon90m/`](../falcon90m/README.md): geração de texto com um LLM
ultra-pequeno via BentoML. O padrão é **`google/gemma-3-270m-it`** (~270M),
bom passo depois do Falcon 90M para instrução e formatação.

---

## Acesso ao modelo (obrigatório na 1ª vez)

O repositório no Hugging Face é **gated**. Passos:

1. Abra <https://huggingface.co/google/gemma-3-270m-it> (é preciso estar logado).
2. Leia e clique em **Agree and access repository** (ou equivalente).
3. No projeto, confira a sessão:

```bash
uv run --no-active hf auth whoami
# se precisar logar de novo:
uv run --no-active hf auth login
```

4. Só então:

```bash
just gemma3_js run
# ou
just gemma3 run
```

Sem o aceite da licença na conta HF, o download devolve **403** mesmo autenticado.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | serviço BentoML com endpoint `/generate` |
| `justfile` | receitas (`serve`, `curl-generate`, ...) |
| `bentofile.yaml` | empacotamento (`just gemma3 build`) |

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

---

## Como rodar

```bash
just gemma3 run               # smoke test, sem HTTP
just gemma3 serve             # terminal 1
just gemma3 curl-generate     # terminal 2
```

| Receita | O que faz |
|---|---|
| `just gemma3 curl-generate-raw` | JSON cru |
| `just gemma3 curl-generate-file` | corpo em `tmp/payload.json` |
| `just gemma3 curl-format` | pedido de JSON estruturado |
| `just gemma3 swagger` | documentação interativa |
| `just gemma3 stop` | derruba o servidor |
| `just gemma3 build` | empacota num *bento* |

---

## Experimentos

**Compare com o Falcon 90M.** Mesmo prompt em `just falcon90m curl-generate`
e `just gemma3 curl-generate` — o 270M costuma seguir melhor a instrução.

**Troque o checkpoint.** No topo de `service.py`: base `gemma-3-270m` ou
`gemma-3-1b-it` (ainda pequeno, um degrau maior).

**Fine-tune depois.** O caso de uso documentado pelo Google para este tamanho
é especializar (ex.: formatação / entidade) e rodar on-device — esta pasta só
expõe o instruct genérico via BentoML.
