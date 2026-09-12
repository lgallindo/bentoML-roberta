# Variante `lfm2_tools` — o menor modelo que chama ferramenta

[← voltar ao README principal](../README.md)

Até aqui, os modelos deste projeto faziam duas coisas: **liam** (QA extrativo,
grifando um trecho) ou **escreviam** ([`falcon90m/`](../falcon90m/README.md),
[`gemma3/`](../gemma3/README.md)).

Nesta pasta o modelo faz uma terceira coisa: **decide**. Ele olha a pergunta,
olha a lista de ferramentas disponíveis, e responde qual delas quer que a
gente execute — e com quais argumentos.

O modelo padrão é o **LFM2-350M**, com 354,5 milhões de parâmetros: o menor
modelo com *tool calling* de fábrica que dá para baixar hoje.

---

## O ciclo tem quatro passos, e o modelo só participa de dois

```
1. modelo   recebe a pergunta + a lista de ferramentas
            -> devolve   consultar_estoque(produto="Cafeteira elétrica")

2. NÓS      executamos a função Python de verdade (lê o CSV, chama a API)
            -> {"produto": "Cafeteira elétrica", "estoque_unidades": 31, ...}

3. modelo   recebe o resultado da função
            -> devolve a frase final

4. NÓS      entregamos a frase ao usuário
```

Repare no passo 2: **o modelo não executa nada.** Ele não abre o CSV, não faz
conexão, não roda código. Ele escreve o *nome* de uma função e os argumentos,
em texto. Quem executa somos nós, com um `if nome in FERRAMENTAS`.

Todo "agente de IA" que você já viu é este laço, com mais enfeites.

Veja acontecendo:

```bash
just lfm2_tools serve-open        # terminal 1
just lfm2_tools curl-chat         # terminal 2
```

---

## A surpresa: 84M de parâmetros a mais, e o mundo muda

A pasta [`gemma3_js/`](../gemma3_js/README.md) termina com uma lição dura: *"o
encanamento funciona e o modelo não"* — o Gemma 3 270M recebe o histórico
inteiro e não consegue usá-lo.

Aqui acontece o contrário, e é surpreendente. Um modelo de **354M** — maior
que o Gemma por apenas 84M — chama a ferramenta certa, com o argumento certo,
**em português**, na primeira tentativa:

```
Pergunta: "Tem Cafeteira elétrica no estoque?"

cru: '<|tool_call_start|>[consultar_estoque(produto="Cafeteira elétrica")]<|tool_call_end|>'
```

A diferença **não é tamanho**. É **treino**. O LFM2 foi treinado com exemplos
de chamada de ferramenta; o Gemma 3 270M não foi.

> Chamar ferramenta não é uma capacidade que "emerge" quando o modelo cresce.
> É um **formato** que alguém ensinou.

Essa distinção vale mais que qualquer tabela de benchmark — e é o motivo de
esta pasta existir.

---

## Cada família inventa um formato diferente

Os três modelos testados aqui pedem exatamente a mesma coisa de três jeitos
incompatíveis:

| família | como pede `consultar_estoque(produto="Cafeteira elétrica")` |
|---|---|
| **LFM2** | `<\|tool_call_start\|>[consultar_estoque(produto="Cafeteira elétrica")]<\|tool_call_end\|>` |
| **Qwen** | `<tool_call>{"name": "consultar_estoque", "arguments": {...}}</tool_call>` |
| **Hammer** | ```` ```[{"name": "consultar_estoque", "arguments": {...}}]``` ```` |

Um é **sintaxe de chamada Python**. Outro é **JSON entre etiquetas**. O
terceiro é uma **lista de JSON dentro de um bloco de markdown** — e ainda usa
aspas simples, que não são JSON válido.

Nenhum é "o" formato. Quando um serviço promete "suporte a tool calling", boa
parte do trabalho é exatamente a função `extrair()` do `ferramentas.py`, que
traduz os três para uma estrutura só.

```bash
just lfm2_tools ferramentas     # mostra os três formatos virando a mesma coisa
```

---

## Onde ele quebra: chamar ferramenta quando não deveria

Aqui está o resultado honesto. O LFM2-350M acerta **sempre** quando deve
chamar. Ele erra quando **não** deve:

```
"Bom dia! Tudo bem?"            -> consultar_estoque(produto="Cafeteira elétrica")
"Me explique o que é um marketplace." -> consultar_estoque(produto="Cafeteira elétrica")
```

Num teste anterior, com uma ferramenta só no esquema, ele chegou a **inventar
produtos** para ter o que chamar:

```
"Bom dia! Tudo bem?"            -> consultar_estoque(produto="Nesun")
"Qual é a capital da França?"   -> consultar_estoque(produto="Paris")
"Obrigado, era só isso."        -> consultar_estoque(produto="Wireless Headphones")
```

Ele aprendeu *"existe ferramenta, logo chame ferramenta"* — não *"decida se
precisa de ferramenta"*.

```bash
just lfm2_tools curl-falhas     # veja ao vivo
```

### O placar, medido

`just lfm2_tools bancada` roda sete casos em três modelos. Quatro dos sete são
perguntas que **não** deveriam acionar nada:

| modelo | parâmetros | decisão | argumentos | tempo |
|---|---:|---:|---:|---:|
| `LiquidAI/LFM2-350M` | 354,5M | **5/7** | 3/3 | 22,2 s |
| `Qwen/Qwen2.5-0.5B-Instruct` | 494,0M | **7/7** | 3/3 | 29,1 s |
| `MadeAgents/Hammer2.1-0.5b` | 493,8M | **7/7** | 3/3 | 27,8 s |

Os três **sabem chamar**: argumentos 3/3 em todos. O que os 140M de
parâmetros a mais compram não é a chamada — é **o bom senso de não chamar**.

Duas observações que só aparecem olhando a saída crua:

- O **Hammer** recusa emitindo uma **lista vazia** (` ```[]``` `), nunca uma
  frase. Ele é um modelo de função pura: acerta as sete decisões e é inútil
  como chatbot, porque não sabe conversar. Medir "acertou/errou" sem olhar o
  cru teria classificado essas recusas como chamadas — foi o que aconteceu na
  primeira versão desta bancada.
- O comportamento do LFM2 **muda com o esquema**. Com uma ferramenta na lista
  ele fez 3/6; com duas, 5/7. Quantas ferramentas você oferece altera quando
  ele resolve usá-las — o que é uma má notícia para quem esperava um número
  estável.

---

## O segundo salto também mostra o tamanho

Quando a ferramenta devolve o resultado, o LFM2-350M escreve a frase final com
os números **certos** — e escorrega no resto:

```
ferramenta -> {"produto": "Cafeteira elétrica", "estoque_unidades": 31,
               "preco_brl": 219.9, "vendedor": "Casa Bonita"}

modelo     -> "Yes, we have 31 Cafeteira elétrica in stock, SKU CAS-001,
               priced at $219.90, with a 3-day delivery window.
               It's currently on sale at Casa Bonita."
```

Três defeitos numa frase só, e nenhum deles é o número:

1. **trocou de idioma** — a pergunta era em português;
2. **trocou de moeda** — `219.90` virou `$219.90`, não `R$ 219,90`;
3. **inventou** — "on sale" (em promoção) não estava no resultado da ferramenta.

O dado chegou certo e a redação estragou. É o mesmo hábito de diagnóstico da
pasta `gemma3_js/`: separar o que é **encanamento** do que é **modelo**. Aqui
o encanamento está impecável — o `passos` da resposta prova isso — e o que
falha é a última frase.

### E às vezes a última frase é ficção pura

O caso mais grave está a um comando de distância:

```bash
just lfm2_tools curl-feriados
```

A ferramenta faz a chamada certa, a BrasilAPI devolve os 14 feriados nacionais
de 2026, corretos, e o modelo escreve:

> "Os feriados de 2026 são: 1. Semana Santa, 2. **Dia da Bênção**, 3. **Feira
> Nacional de São João**, 4. **Dia dos Namorados**, 5. Dia da Independência,
> 6. **Dia da Independência dos Trabalhadores**, 7. **Dia dos Namorados da
> Independência**…"

Nada disso existe. Não há "Dia da Bênção" no calendário nacional, Dia dos
Namorados não é feriado, e "Dia dos Namorados da Independência" não é sequer
uma data. O modelo recebeu a lista certa e **inventou outra**.

Guarde esta tela. Ela é o argumento mais curto que existe contra a ideia de
que "o RAG resolve alucinação" — e contra a de que ferramenta resolve. O dado
correto esteve dentro do processo o tempo todo, no campo `passos`, e mesmo
assim não chegou ao usuário.

O conserto, aqui, nem é de modelo: para uma lista de feriados, **mostre o
retorno da ferramenta** e não peça ao modelo para reescrevê-lo. Nem toda
resposta precisa passar pelo segundo salto. Saber quais precisam é decisão de
projeto, e é sua, não do modelo.

---

## As ferramentas são de verdade

Nenhuma das duas é simulada:

| ferramenta | o que faz |
|---|---|
| `consultar_estoque(produto)` | lê o mesmo CSV de 25 produtos da variante [`inventario/`](../inventario/README.md) |
| `consultar_feriados(ano)` | chama a **BrasilAPI**, a mesma da variante [`api/`](../api/README.md) |

A segunda vale um comentário. Na variante `api/`, a chamada externa acontecia
na **inicialização**: o contexto entrava sempre, quisesse você ou não. Aqui a
mesma chamada acontece **só quando o modelo decide pedir**. É a diferença
entre um serviço que busca dado e um serviço que *decide* buscar dado — e é
onde mora todo o risco novo dos agentes.

```bash
just lfm2_tools curl-feriados   # sai para a internet de verdade
```

---

## O que tem nesta pasta

| Arquivo | O que é |
|---|---|
| `ferramentas.py` | as funções, o JSON Schema e o tradutor dos 3 formatos |
| `service.py` | o serviço: `/chat`, `/tool_call` e `/tools` |
| `bancada.py` | o benchmark dos três modelos |
| `context/estoque_marketplace.csv` | o mesmo CSV da variante `inventario/` |

---

## Como rodar

```bash
just lfm2_tools ferramentas    # as funções sozinhas, sem modelo (instantâneo)
just lfm2_tools run            # o ciclo completo, sem servidor
just lfm2_tools serve-open     # sobe na 8080
just lfm2_tools bancada        # os 3 modelos lado a lado (~2,8 GB na 1a vez)
```

Com o servidor de pé, em outro terminal:

| Receita | O que faz |
|---|---|
| `just lfm2_tools curl-tool-call` | só o 1º salto: o texto **cru** que o modelo cuspiu |
| `just lfm2_tools curl-chat` | o ciclo completo, com o campo `passos` |
| `just lfm2_tools curl-feriados` | a ferramenta que sai para a BrasilAPI |
| `just lfm2_tools curl-falhas` | onde ele chama ferramenta sem precisar |
| `just lfm2_tools curl-tools` | o esquema que o modelo lê |

Para trocar de modelo sem editar código:

```bash
MODELO=Qwen/Qwen2.5-0.5B-Instruct just lfm2_tools run
```

---

## Experimentos

**Leia o campo `cru`.** Rode `curl-tool-call` e olhe o texto que o modelo
gerou, antes de qualquer interpretação. Não há mágica: é uma string. Todo o
resto — executar a função, montar a resposta — é código Python comum que você
consegue ler inteiro em `service.py`.

**Apague uma ferramenta do esquema.** Em `ferramentas.py`, comente a entrada
de `consultar_feriados` no `ESQUEMA` e pergunte sobre feriados assim mesmo. O
modelo vai tentar usar `consultar_estoque` para responder — porque é a única
que sobrou.

**Minta na descrição.** Troque a `description` de `consultar_estoque` por algo
errado ("consulta a previsão do tempo") e veja quando o modelo passa a chamá-la.
A descrição não é documentação: é **prompt**. É o único lugar onde você
consegue influenciar a decisão dele.

**Meça o seu próprio caso.** Acrescente perguntas ao `CASOS` do `bancada.py` —
principalmente perguntas que **não** deveriam acionar ferramenta. É essa lista
que decide se um modelo pequeno serve para o seu problema, e ela é diferente
para cada aplicação.

**Compare com `falcon90m_apps/`.** Aquela pasta faz algo parecido sem nenhum
suporte nativo: força o Falcon 90M a devolver JSON na base do *prompt* e
conserta o resto com regex e heurística. Vale ver as duas abordagens lado a
lado — uma pede um formato que o modelo conhece, a outra implora por um que
ele não conhece.
