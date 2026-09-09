# Variante `gemma3_gradio` — a mesma interface, sem escrever front-end

[← voltar ao README principal](../README.md)

Pasta irmã da [`gemma3_js/`](../gemma3_js/README.md): mesmo modelo, mesmo
endpoint `POST /chat`, mesma interface de conversa em `/ui`. A diferença é
**quem escreveu a tela**.

| | [`gemma3_js/`](../gemma3_js/README.md) | **`gemma3_gradio/`** |
|---|---|---|
| a interface | `index.html` + `app.js` escritos à mão | `gr.ChatInterface(...)` |
| linhas de front-end | ~120 entre HTML e JS | **1 chamada de função** |
| quem guarda a conversa | um `const messages = []` no navegador | o Gradio, por dentro |
| dá para ver o mecanismo? | sim, linha por linha | não, e é essa a graça |
| dependência extra | nenhuma | `gradio>=5,<6` (~100 MB) |

Ter as duas lado a lado é o ponto. Uma mostra **como** funciona; a outra mostra
**quanto** disso dá para não escrever.

---

## O que se espera deste programa

Um chat que funciona no navegador. Suba e abra <http://127.0.0.1:8080/ui/>:

```python
demo = gr.ChatInterface(
    fn=_gradio_respond,
    title="Gemma 3 270M",
    description="Chat multi-turn (histórico no Gradio → API /chat).",
    type="messages",
)
```

Isso é a interface inteira. Caixa de texto, botão de enviar, balões de
conversa, histórico na tela, botão de limpar, layout que funciona no celular —
tudo vem de `gr.ChatInterface`.

A função `_gradio_respond` é a cola entre o Gradio e a API do serviço:

```python
def _gradio_respond(message: str, history: list):
    messages = []
    for item in history or []:            # o Gradio entrega o histórico
        role, content = item.get("role"), item.get("content")
        if role in {"user", "assistant", "system"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return _SERVICE.chat(messages=messages, max_new_tokens=128)["text"]
```

Repare no `type="messages"`: é ele que faz o Gradio entregar o histórico já no
formato `{"role": ..., "content": ...}` que o `/chat` espera. Sem isso, o
Gradio usa um formato antigo de pares e a conversão fica na sua conta.

---

## A memória continua não estando no servidor

Vale insistir, porque o Gradio esconde isso bem: o serviço continua **sem
estado**. Não há sessão, não há banco, não há dicionário de usuários. A
diferença é só quem carrega o histórico até a chamada:

- na variante `gemma3_js/`, um array JavaScript que você mesmo escreveu;
- aqui, o componente do Gradio, que faz a mesma coisa e não te conta.

O `_gradio_respond` recebe `history` pronto e remonta a lista `messages`
inteira a cada turno — igualzinho ao `app.js` da outra pasta. Toda a discussão
sobre custo crescente por turno, escala horizontal e o F5 que apaga tudo vale
aqui do mesmo jeito, e está explicada em detalhe no
[README da `gemma3_js/`](../gemma3_js/README.md).

Este é o preço de um framework de UI: ele acerta por você e, por isso, você
pode passar meses sem entender o que ele acertou. Comece pela pasta `gemma3_js/`
se a pergunta for "como funciona"; venha para esta se a pergunta for "como
entrego isso hoje".

---

## O modelo continua não dando conta

O mesmo teste da pasta irmã, com o mesmo resultado honesto:

```
user:      "My name is Ada."
assistant: "Hi Ada!"
user:      "What is my name?"

resposta:  "I am a large language model, for you, my friend..."
```

`prompt_tokens: 33` confirma que as três mensagens chegaram ao modelo. Ele
simplesmente não é grande o bastante para usá-las. Interface bonita não
conserta modelo pequeno — e é bom ver isso com os próprios olhos numa tela que
parece um ChatGPT.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço, a função-cola e o `gr.ChatInterface` |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento: precisa de `gradio` e `fastapi` |

Não há pasta `static/`: não há nada estático para servir.

O encaixe no BentoML é o mesmo da pasta irmã — o Gradio é montado num FastAPI,
e o FastAPI vira um app ASGI pendurado no serviço:

```python
app = FastAPI()
return gr.mount_gradio_app(app, demo, path="/")
...
@bentoml.asgi_app(_build_gradio_app(), path="/ui")
```

O mesmo processo serve a API em `/chat` e a interface em `/ui/`, na mesma
porta.

---

## Como rodar

O modelo é *gated* no Hugging Face. Na primeira vez:

1. aceite a licença em <https://huggingface.co/google/gemma-3-270m-it>
2. `uv run --no-active hf auth login`

Depois, prefira a porta 8080 para deixar a faixa 3xxx livre:

```bash
just gemma3_gradio serve-open     # terminal 1, sobe na 8080
```

Abra <http://127.0.0.1:8080/ui/> e converse.

| Receita | O que faz |
|---|---|
| `just gemma3_gradio run` | teste multi-turn sem servidor e sem HTTP |
| `just gemma3_gradio serve-open` | sobe na 8080 (fora da faixa 3xxx) |
| `PORT=8080 just gemma3_gradio curl-chat` | manda três mensagens pela API |
| `PORT=8080 just gemma3_gradio curl-generate` | o `/generate` de turno único |
| `just gemma3_gradio open-ui` | abre a interface no navegador |
| `PORT=8080 just gemma3_gradio stop` | derruba o servidor |

A primeira subida demora mais que as outras variantes: além do modelo, o Gradio
precisa carregar.

---

## Experimentos

**Converse pela tela e pelo `curl` ao mesmo tempo.** Com o servidor de pé, use
a interface e, no terminal, rode `curl-chat`. As duas conversas não se
enxergam: são históricos diferentes chegando no mesmo serviço sem estado.

**Meça o que o Gradio custa.** Compare o tempo de subida com o da variante
`gemma3/`, que não tem interface. Compare também o tamanho do `.venv` antes e
depois de instalar o `gradio`. Interface pronta é conveniência paga.

**Troque o título e a descrição.** Mexa nos argumentos do `gr.ChatInterface` e
suba de novo. Em quanto tempo você conseguiria a mesma mudança na pasta
`gemma3_js/`?

**Ache o limite do atalho.** Tente mudar alguma coisa que o `ChatInterface` não
oferece como argumento — a cor de um balão, a ordem dos botões. Aqui é que o
framework começa a cobrar: o que ele não previu custa mais caro do que teria
custado escrever à mão desde o começo.

**Aumente `max_new_tokens` na função-cola.** Ela fixa 128. Suba para 512 e veja
a resposta ficar mais longa e mais lenta. Repare que a interface não oferece
esse controle ao usuário — decisões que o `gr.ChatInterface` não expõe ficam
escondidas no seu código.
