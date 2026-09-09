"""Busca feriados nacionais numa API externa e transforma em prosa para QA extrativo.

Como esta variante difere das outras
------------------------------------
Nas outras variantes o contexto já está no disco antes de o serviço subir:

    basico/       o contexto vem na requisição
    pdf/          o contexto são dois PDFs em context/
    inventario/   o contexto é um CSV em context/

Aqui o contexto **não existe** até o serviço subir. Ele é buscado na BrasilAPI
(<https://brasilapi.com.br>, aberta, sem chave) e só então convertido em prosa.
Isso acrescenta três problemas que arquivo em disco não tem, e os três são o
motivo pedagógico desta pasta existir:

1. **A rede pode falhar.** Um serviço que morre na inicialização porque a API
   externa está fora do ar é um serviço frágil. Por isso `carregar_feriados()`
   grava um cache em `context/` a cada busca bem-sucedida e cai nele quando a
   busca falha. O serviço sobe de qualquer jeito, e diz de onde veio o contexto.
2. **A resposta pode mudar.** O mesmo `answer()` com a mesma pergunta pode
   devolver coisas diferentes em dias diferentes, porque o contexto é outro.
   Nenhuma métrica de servidor percebe isso.
3. **O JSON não é prosa.** Modelo de QA extrativo grifa um trecho de texto
   corrido; ele não navega estrutura. `feriado_para_texto()` faz o mesmo
   trabalho que `inventario.py` faz com o CSV.
"""

import json
import os
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

URL_BASE = "https://brasilapi.com.br/api/feriados/v1"
TIMEOUT_S = 10

# A BrasilAPI responde 403 para o User-Agent padrão do urllib
# ("Python-urllib/3.13"). Não é bug do nosso lado: é a API recusando cliente
# que não se identifica. Toda integração externa tem uma regra dessas, e
# descobrir qual é faz parte do trabalho.
CABECALHOS = {"User-Agent": "qa-demo-cesar/1.0 (material didatico)"}

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def _cache_path(ano: int) -> Path:
    return Path(__file__).parent / "context" / f"feriados-{ano}.json"


def _por_extenso(iso: str) -> str:
    """'2026-02-16' -> '16 de fevereiro de 2026'"""
    a, m, d = iso.split("-")
    return f"{int(d)} de {MESES[int(m) - 1]} de {a}"


def buscar_feriados(ano: int) -> tuple[list[dict], str]:
    """Busca na API; em caso de falha, cai no cache. Devolve (dados, origem)."""
    try:
        pedido = urllib.request.Request(f"{URL_BASE}/{ano}", headers=CABECALHOS)
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as resposta:
            dados = json.load(resposta)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
        cache = _cache_path(ano)
        if not cache.exists():
            raise RuntimeError(
                f"A API não respondeu ({erro}) e não há cache em {cache}. "
                f"Rode `just api atualizar` com rede para criar o cache."
            ) from erro
        return json.loads(cache.read_text(encoding="utf-8")), f"cache ({cache.name})"

    # Só grava o cache quando a busca deu certo, para nunca sobrescrever um
    # cache bom com uma resposta pela metade.
    _cache_path(ano).write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dados, "BrasilAPI"


def feriado_para_texto(item: dict) -> str:
    """Converte um feriado do JSON em frases de contexto para o modelo.

    Cada frase repete o nome do feriado, pela mesma razão que `inventario.py`
    repete o nome do produto: o modelo fatia o contexto em janelas, e uma frase
    que só diz "ele cai numa segunda-feira" fica inútil quando é separada da
    frase anterior.

    O FORMATO DESTAS TRÊS FRASES FOI ESCOLHIDO MEDINDO, NÃO ADIVINHANDO.

    A primeira versão dizia "O feriado X acontece em <data>. O feriado X cai
    numa <dia>. A data <data> é feriado nacional por causa de X." Parece
    equivalente, e com 5 feriados no contexto ela até funcionava. Com os 14
    feriados de verdade ela acertava 4 de 7 perguntas: "Quando é o Carnaval?"
    respondia "segunda-feira", e "Em que dia da semana cai o Natal?" respondia
    vazio.

    A versão abaixo acerta 6 de 7 no mesmo contexto. O que mudou foi só a
    redação: a data aparece em DUAS frases com ordens diferentes ("no dia D
    comemora-se X" além de "X é comemorado no dia D"), e o dia da semana ficou
    atrás da expressão literal "dia da semana", que é o que a pergunta usa.

    A lição é a da variante pdf/ outra vez, e mais fina: não é só o tamanho do
    contexto que decide a resposta -- é a redação dele. Mesma API, mesmo
    modelo, mesmas perguntas, 4/7 contra 6/7.
    """
    nome = item["name"]
    data = _por_extenso(item["date"])
    dia_semana = item["weekday"]

    return " ".join(
        [
            f"O feriado {nome} é comemorado no dia {data}.",
            f"No dia {data} comemora-se o feriado {nome}.",
            f"O feriado {nome} cai em um dia da semana que é {dia_semana}.",
        ]
    )


def carregar_feriados(ano: int | None = None) -> tuple[str, str, int]:
    """API -> um parágrafo de prosa por feriado. Devolve (prosa, origem, quantidade)."""
    ano = ano or int(os.environ.get("FERIADOS_ANO", "2026"))
    dados, origem = buscar_feriados(ano)
    blocos = [feriado_para_texto(item) for item in dados]
    prosa = unicodedata.normalize("NFC", "\n\n".join(blocos))
    return prosa, f"{origem}, ano {ano}", len(dados)


if __name__ == "__main__":
    # Mostra o contexto gerado sem carregar o modelo nem subir servidor.
    prosa, origem, quantos = carregar_feriados()
    print(f"[contexto] {quantos} feriados, origem: {origem}")
    print(f"[contexto] {len(prosa)} caracteres\n")
    print(prosa)
