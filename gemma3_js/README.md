# Variante `gemma3_js` — chat multi-turn, e quem guarda a memória

[← voltar ao README principal](../README.md)

Mesmo modelo da variante [`gemma3/`](../gemma3/README.md), com duas coisas a
mais: um endpoint `POST /chat` que aceita a conversa inteira, e uma interface
web em `/ui/` feita à mão — um `index.html` e um `app.js`, sem framework
nenhum.

A pasta existe para responder uma pergunta que quase todo mundo erra na
primeira vez: **onde fica a memória de um chatbot?**

---

## A resposta: no cliente. O servidor não lembra de nada.

Olhe o serviço. Não há lista, não há dicionário de sessões, não há banco:

```python
@bentoml.api
def chat(self, messages: list[dict], max_new_tokens: int = 64, ...) -> dict:
    """Chat multi-turn: o cliente JS envia o histórico completo."""
    return self._generate_from_messages(messages, max_new_tokens, temperature)
```

O parâmetro é `messages` — a conversa **inteira**, toda vez. Agora olhe o
cliente, em `static/app.js`:

```js
const messages = [];          // a memória do chat mora aqui, no navegador
...
messages.push({ role: "user", content: text });
// e o POST manda o array inteiro:
body: JSON.stringify({ messages, max_new_tokens: 128, temperature: 0.0 })
...
messages.push({ role: "assistant", content: reply });
```

O servidor é **sem estado** (*stateless*). Cada requisição chega, é atendida e
esquecida. Isso não é preguiça de implementação — é o desenho que permite:

- **escalar horizontalmente**: qualquer réplica atende qualquer mensagem, porque
  nenhuma delas sabe mais que as outras;
- **reiniciar sem perder conversa**: derrube e suba o servidor no meio do chat;
  a página continua funcionando, porque a conversa nunca esteve lá;
- **o F5 apagar tudo**: a memória mora num `const messages = []` do JavaScript,
  então recarregar a página zera a conversa. Esse é o preço.

É exatamente assim que a API da OpenAI, da Anthropic e da Google funcionam.
Quando você conversa com um chatbot desses, o histórico inteiro sobe de novo a
cada mensagem.

### A consequência que liga esta pasta à série `stride`

Se a conversa inteira é reenviada a cada turno, **o custo cresce a cada turno**.
Uma conversa de 20 mensagens manda as 20 na vigésima requisição. É por isso que
`prompt_tokens` vem na resposta:

```json
{"text": "...", "prompt_tokens": 33, "completion_tokens": 34}
```

Aqueles 33 são as três mensagens do teste somadas, não só a última. Acompanhe
esse número subir enquanto conversa: é a mesma contabilidade das variantes
[`*_usage`](../inventario_stride_usage/README.md), agora crescendo sozinha.

---

## O modelo não consegue usar a memória que você mandou

Vale ser honesto sobre o resultado. O `just gemma3_js run` faz este teste:

```
user:      "My name is Ada."
assistant: "Hi Ada!"
user:      "What is my name?"
```

E o Gemma 3 270M responde:

```
"I am a large language model, for you, my friend. I am here to help you
 with any questions or tasks you have. I am ready to assist!"
```

Não é "Ada". **O encanamento funciona e o modelo não.** O `prompt_tokens: 33`
prova que as três mensagens chegaram; o modelo simplesmente é pequeno demais
para fazer o que se pede com elas.

Separar essas duas coisas é o hábito que a pasta quer ensinar. "O chat não
lembra do meu nome" pode ser um bug de transporte (o histórico não foi enviado)
ou um limite do modelo (foi enviado e ignorado). São diagnósticos diferentes,
com consertos diferentes, e `prompt_tokens` é o que distingue um do outro.

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `service.py` | o serviço: `/chat`, `/generate` e o app web montado em `/ui` |
| `static/index.html` | a página do chat |
| `static/app.js` | o cliente: **é aqui que a conversa mora** |
| `justfile` | as receitas desta variante |
| `bentofile.yaml` | empacotamento: o `.py` **e** a pasta `static/` |

### Como uma página estática entra num serviço BentoML

```python
web = FastAPI()

@web.get("/")
async def ui_index():
    return FileResponse(STATIC_DIR / "index.html")

@bentoml.service(resources={"cpu": "2"})
@bentoml.asgi_app(web, path="/ui")
class QAService:
    ...
```

O `@bentoml.asgi_app` pendura um aplicativo ASGI qualquer — aqui um FastAPI —
dentro do serviço, no caminho `/ui`. O mesmo processo passa a servir a API em
`/chat` e a página em `/ui/`, na mesma porta. Sem CORS, sem segundo servidor,
sem `python -m http.server` ao lado.

Repare que `static/` precisa estar no `include:` do `bentofile.yaml`. Esquecer
disso gera um bento que sobe e responde a API, mas devolve 404 na interface —
um erro que só aparece depois de empacotar.

---

## Como rodar

O modelo é *gated* no Hugging Face. Na primeira vez:

1. aceite a licença em <https://huggingface.co/google/gemma-3-270m-it>
2. `uv run --no-active hf auth login`

Depois, prefira a porta 8080 para deixar a faixa 3xxx livre para as outras
variantes:

```bash
just gemma3_js serve-open        # terminal 1, sobe na 8080
```

Abra <http://127.0.0.1:8080/ui/> e converse. Ou, pelo terminal 2:

```bash
PORT=8080 just gemma3_js curl-chat
```

| Receita | O que faz |
|---|---|
| `just gemma3_js run` | teste multi-turn sem servidor e sem HTTP |
| `just gemma3_js serve-open` | sobe na 8080 (fora da faixa 3xxx) |
| `PORT=8080 just gemma3_js curl-chat` | manda três mensagens e vê a resposta |
| `PORT=8080 just gemma3_js curl-generate` | o `/generate` de turno único |
| `just gemma3_js open-ui` | abre a interface no navegador |
| `PORT=8080 just gemma3_js stop` | derruba o servidor |

---

## Experimentos

**Prove que o servidor não lembra.** Converse três ou quatro mensagens na
interface. Agora, sem fechar a aba, derrube o servidor (`stop`) e suba de novo.
Mande outra mensagem. Funciona — porque a conversa estava no seu navegador o
tempo todo.

**Prove que o cliente lembra.** Aperte F5. Sumiu tudo. A memória era um array
JavaScript, e você acabou de recarregá-lo vazio.

**Veja o `prompt_tokens` crescer.** Abra o console do navegador (F12) e olhe as
respostas do `/chat` a cada mensagem. O número sobe a cada turno, mesmo que
suas mensagens tenham o mesmo tamanho. Em 20 turnos, quanto custa a vigésima?

**Corte o histórico e veja o que muda.** Em `app.js`, mande só as últimas duas
mensagens em vez do array inteiro (`messages.slice(-2)`). O custo para de
crescer — e a conversa fica ainda mais amnésica. Essa é a decisão de projeto
real de todo chatbot: quanto de passado vale a pena pagar.

**Compare com `/generate`.** O endpoint `/generate` recebe um `prompt` só, sem
histórico. Rode `curl-generate` e `curl-chat` lado a lado: mesmo modelo, mesma
inferência, APIs diferentes. Multi-turn não é uma capacidade do modelo — é um
formato de requisição.

**Confira a versão Gradio.** A pasta
[`gemma3_gradio/`](../gemma3_gradio/README.md) faz o mesmo com ~10 linhas de
Python em vez de um `app.js`. Vale comparar o que cada abordagem esconde.
