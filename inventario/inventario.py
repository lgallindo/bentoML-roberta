"""Transforma o CSV de estoque em prosa apropriada para QA extrativo.

Modelos de QA extrativo (BERTimbau, XLM-R) são treinados em texto corrido, não
em tabelas. Colar as linhas cruas do CSV dentro do `context` produz respostas
ruins: o modelo não entende que a coluna "preco_brl" se refere ao produto que
está três colunas atrás. Aqui cada linha vira algumas frases curtas, e cada
frase repete o nome do produto -- assim o trecho continua encontrável mesmo
quando o modelo fatia o contexto e separa uma linha das suas vizinhas.
"""

import csv
import unicodedata
from pathlib import Path


def _brl(valor: str) -> str:
    """'189.90' -> 'R$ 189,90'"""
    return f"R$ {float(valor):.2f}".replace(".", ",")


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def linha_para_texto(row: dict) -> str:
    produto = row["produto"]
    estoque = int(row["estoque_unidades"])
    prazo = int(row["prazo_envio_dias"])
    garantia = int(row["garantia_meses"])

    frases = [
        f"O produto {produto} (SKU {row['sku']}) pertence à categoria "
        f"{row['categoria']} e custa {_brl(row['preco_brl'])}."
    ]

    if estoque == 0:
        frases.append(
            f"O produto {produto} está esgotado e não possui unidades em estoque."
        )
    else:
        frases.append(
            f"O estoque atual de {produto} é de {estoque} "
            f"{_plural(estoque, 'unidade', 'unidades')}."
        )

    frases.append(
        f"O prazo de envio de {produto} é de {prazo} "
        f"{_plural(prazo, 'dia útil', 'dias úteis')}."
    )
    frases.append(
        f"O produto {produto} é vendido por {row['vendedor']}, "
        f"em {row['cidade_uf']}, com garantia de {garantia} "
        f"{_plural(garantia, 'mês', 'meses')}."
    )

    return " ".join(frases)


def carregar_estoque(csv_path: str | Path) -> str:
    """CSV -> um parágrafo de prosa por produto, com linha em branco entre eles."""
    with open(csv_path, encoding="utf-8", newline="") as fh:
        blocos = [linha_para_texto(row) for row in csv.DictReader(fh)]
    return unicodedata.normalize("NFC", "\n\n".join(blocos))


if __name__ == "__main__":
    # Mostra o começo do contexto gerado, para conferir a formatação sem
    # precisar carregar o modelo nem subir servidor.
    print(
        carregar_estoque(Path(__file__).parent / "context" / "estoque_marketplace.csv")[
            :600
        ]
    )
