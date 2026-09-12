"""As ferramentas de verdade, e o tradutor entre elas e o modelo.

Três coisas moram aqui, e vale separar as três na cabeça:

    FERRAMENTAS   funções Python comuns. Leem um CSV, chamam uma API. Não
                  sabem que existe modelo de linguagem nenhum.

    ESQUEMA       a descrição das ferramentas no formato JSON Schema, que é
                  o que entra no `tools=[...]` do chat template. É isto que
                  o modelo lê para saber o que pode pedir.

    EXTRAIR       o tradutor de volta: pega o texto que o modelo cuspiu e
                  descobre qual ferramenta ele quis chamar, com quais
                  argumentos.

O terceiro é o que quase ninguém espera precisar escrever, e é onde mora a
surpresa desta pasta: **cada família de modelo inventa um formato diferente
para dizer a mesma coisa.** Os três modelos testados aqui pedem
`consultar_estoque(produto="Cafeteira elétrica")` assim:

    LFM2     <|tool_call_start|>[consultar_estoque(produto="Cafeteira")]<|tool_call_end|>
    Qwen     <tool_call>{"name": "consultar_estoque", "arguments": {...}}</tool_call>
    Hammer   ```[{"name": "consultar_estoque", "arguments": {...}}]```

Um é sintaxe de chamada de função Python, outro é JSON entre etiquetas, o
terceiro é uma LISTA de JSON dentro de um bloco de código markdown. Nenhum é
"o" formato. Quando um serviço promete "suporte a tool calling", boa parte do
trabalho é exatamente esta função `extrair`.
"""

from __future__ import annotations

import ast
import csv
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

CSV = Path(__file__).parent / "context" / "estoque_marketplace.csv"
BRASIL_API = "https://brasilapi.com.br/api/feriados/v1/{ano}"


# ---------------------------------------------------------------------------
# 1. AS FERRAMENTAS -- Python comum, sem nada de IA
# ---------------------------------------------------------------------------

def _chave(texto: str) -> str:
    """Minúscula e sem acento, para comparar nome de produto sem sofrer."""
    sem = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem if not unicodedata.combining(c)).strip()


def consultar_estoque(produto: str) -> dict:
    """Procura um produto no CSV do marketplace e devolve preço e estoque.

    Repare que a busca é tolerante: o modelo dificilmente vai escrever o nome
    do produto exatamente como está no CSV. Se ele pedir "cafeteira", a gente
    aceita. Ferramenta que só funciona com o argumento perfeito não sobrevive
    a um modelo de 350M de parâmetros.
    """
    alvo = _chave(produto)
    if not alvo:
        return {"erro": "produto vazio"}

    with open(CSV, encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    exatos = [l for l in linhas if _chave(l["produto"]) == alvo]
    parciais = [l for l in linhas if alvo in _chave(l["produto"])]
    if not exatos and not parciais:
        # Tenta ainda por palavra solta ("fone" acha "Fone de ouvido Bluetooth")
        palavras = [p for p in alvo.split() if len(p) > 3]
        parciais = [
            l for l in linhas if any(p in _chave(l["produto"]) for p in palavras)
        ]

    achado = (exatos or parciais)
    if not achado:
        return {
            "encontrado": False,
            "produto_procurado": produto,
            "aviso": "Produto não existe neste marketplace.",
        }

    linha = achado[0]
    return {
        "encontrado": True,
        "produto": linha["produto"],
        "sku": linha["sku"],
        "preco_brl": float(linha["preco_brl"]),
        "estoque_unidades": int(linha["estoque_unidades"]),
        "prazo_envio_dias": int(linha["prazo_envio_dias"]),
        "vendedor": linha["vendedor"],
    }


def consultar_feriados(ano: int) -> dict:
    """Busca os feriados nacionais de um ano na BrasilAPI.

    É a MESMA chamada da variante api/, agora acionada pelo modelo em vez de
    acontecer na inicialização. A diferença é o que interessa: lá o contexto
    externo entrava sempre; aqui ele entra só quando o modelo decide pedir.
    """
    try:
        ano = int(ano)
    except (TypeError, ValueError):
        return {"erro": f"ano inválido: {ano!r}"}

    if not 1900 <= ano <= 2200:
        return {"erro": f"ano fora de faixa: {ano}"}

    url = BRASIL_API.format(ano=ano)
    try:
        with urllib.request.urlopen(url, timeout=10) as resposta:
            feriados = json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
        # Ferramenta que cai não pode derrubar o serviço. Ela DEVOLVE o erro,
        # e quem chamou decide o que fazer -- inclusive contar para o usuário.
        return {"erro": f"BrasilAPI indisponível: {type(erro).__name__}"}

    return {
        "ano": ano,
        "total": len(feriados),
        "feriados": [{"data": f["date"], "nome": f["name"]} for f in feriados],
    }


FERRAMENTAS = {
    "consultar_estoque": consultar_estoque,
    "consultar_feriados": consultar_feriados,
}


# ---------------------------------------------------------------------------
# 2. O ESQUEMA -- o que o modelo lê para saber o que pode pedir
# ---------------------------------------------------------------------------

ESQUEMA = [
    {
        "type": "function",
        "function": {
            "name": "consultar_estoque",
            "description": (
                "Consulta preço, estoque e prazo de envio de um produto do "
                "marketplace. Use somente quando o usuário perguntar sobre um "
                "produto específico."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "produto": {
                        "type": "string",
                        "description": "Nome do produto, ex: 'Cafeteira elétrica'",
                    }
                },
                "required": ["produto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_feriados",
            "description": (
                "Lista os feriados nacionais brasileiros de um ano. Use somente "
                "quando o usuário perguntar sobre feriados ou datas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer", "description": "Ano com 4 dígitos"}
                },
                "required": ["ano"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 3. EXTRAIR -- o tradutor de volta, um jeito por família de modelo
# ---------------------------------------------------------------------------

_LFM2 = re.compile(r"<\|tool_call_start\|>(.*?)<\|tool_call_end\|>", re.S)
_QWEN = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
_CERCA = re.compile(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", re.S)


def extrair(texto: str) -> list[dict]:
    """Descobre quais ferramentas o modelo pediu. Lista vazia = não pediu nada.

    A lista vazia é uma resposta legítima e importante: quando o usuário diz
    "bom dia", o certo é NÃO chamar ferramenta nenhuma. Veja no README o que
    cada modelo faz nesse caso -- é onde eles mais se diferenciam.
    """
    # --- LFM2: sintaxe de chamada de função Python ---
    achado = _LFM2.search(texto)
    if achado:
        return _ler_chamadas_python(achado.group(1))

    # --- Qwen: um JSON por etiqueta <tool_call> ---
    chamadas = [_normalizar(json.loads(m)) for m in _QWEN.findall(texto)]
    if chamadas:
        return [c for c in chamadas if c]

    # --- Hammer e parecidos: bloco de código com uma lista de JSON ---
    achado = _CERCA.search(texto)
    if achado:
        try:
            # literal_eval em vez de json.loads porque alguns modelos usam
            # aspas simples, que não são JSON válido mas são Python válido.
            dados = ast.literal_eval(achado.group(1))
        except (ValueError, SyntaxError):
            return []
        if isinstance(dados, dict):
            dados = [dados]
        return [c for c in (_normalizar(d) for d in dados) if c]

    return []


def _ler_chamadas_python(trecho: str) -> list[dict]:
    """`[consultar_estoque(produto="X")]` -> [{'name':..., 'arguments':{...}}]"""
    trecho = trecho.strip()
    try:
        arvore = ast.parse(trecho, mode="eval").body
    except SyntaxError:
        return []

    nos = arvore.elts if isinstance(arvore, ast.List) else [arvore]
    chamadas = []
    for no in nos:
        if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Name):
            continue
        try:
            argumentos = {
                palavra.arg: ast.literal_eval(palavra.value)
                for palavra in no.keywords
            }
        except ValueError:
            continue
        chamadas.append({"name": no.func.id, "arguments": argumentos})
    return chamadas


def _normalizar(dado: dict) -> dict | None:
    """Aceita {'name':..,'arguments':..} e a variante com 'parameters'."""
    if not isinstance(dado, dict) or "name" not in dado:
        return None
    argumentos = dado.get("arguments", dado.get("parameters", {}))
    if not isinstance(argumentos, dict):
        argumentos = {}
    return {"name": dado["name"], "arguments": argumentos}


def executar(chamada: dict) -> dict:
    """Roda de verdade a ferramenta que o modelo pediu.

    Duas guardas que parecem paranoia e não são:

      1. o nome precisa estar no dicionário FERRAMENTAS. O modelo pode pedir
         uma função que não existe -- inclusive uma que ele inventou.
      2. os argumentos são passados por NOME. Se o modelo mandar um argumento
         a mais, ou com o nome errado, a chamada falha de forma controlada em
         vez de estourar um TypeError no meio do serviço.
    """
    nome = chamada.get("name")
    funcao = FERRAMENTAS.get(nome)
    if funcao is None:
        return {"erro": f"ferramenta desconhecida: {nome!r}"}
    try:
        return funcao(**chamada.get("arguments", {}))
    except TypeError as erro:
        return {"erro": f"argumentos inválidos para {nome}: {erro}"}


if __name__ == "__main__":
    # Rode com:  uv run --no-active python ferramentas.py
    # As ferramentas sozinhas, sem modelo nenhum no caminho.
    print("consultar_estoque('Fone de ouvido Bluetooth'):")
    print(" ", consultar_estoque("Fone de ouvido Bluetooth"))
    print("\nconsultar_estoque('cafeteira'):   # nome parcial, de propósito")
    print(" ", consultar_estoque("cafeteira"))
    print("\nconsultar_estoque('bicicleta'):   # não existe")
    print(" ", consultar_estoque("bicicleta"))

    if os.environ.get("TESTAR_API"):
        print("\nconsultar_feriados(2026):")
        print(" ", consultar_feriados(2026))

    print("\n--- extrair(), os três formatos ---")
    exemplos = {
        "LFM2": '<|tool_call_start|>[consultar_estoque(produto="Cafeteira elétrica")]<|tool_call_end|>',
        "Qwen": '<tool_call>\n{"name": "consultar_estoque", "arguments": {"produto": "Cafeteira elétrica"}}\n</tool_call>',
        "Hammer": "```\n[{'name': 'consultar_estoque', 'arguments': {'produto': 'Cafeteira elétrica'}}]\n```",
        "nenhuma": "Bom dia! Como posso ajudar?",
    }
    for familia, cru in exemplos.items():
        print(f"  {familia:9} -> {extrair(cru)}")
