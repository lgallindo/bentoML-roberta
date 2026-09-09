"""Converte o CSV de estoque em prosa para QA extrativo."""

import csv
import unicodedata
from pathlib import Path


def format_brl(value: str) -> str:
    """Converte '189.90' em 'R$ 189,90'."""
    return f"R$ {float(value):.2f}".replace(".", ",")


def pluralize(number: int, singular: str, plural: str) -> str:
    """Retorna a forma singular para um item e a plural para os demais."""
    return singular if number == 1 else plural


def row_to_text(row: dict) -> str:
    """Converte uma linha do CSV em frases de contexto para o modelo."""
    product = row["produto"]
    stock = int(row["estoque_unidades"])
    shipping_days = int(row["prazo_envio_dias"])
    warranty_months = int(row["garantia_meses"])
    sentences = [
        f"O produto {product} (SKU {row['sku']}) pertence à categoria "
        f"{row['categoria']} e custa {format_brl(row['preco_brl'])}."
    ]
    if stock == 0:
        sentences.append(
            f"O produto {product} está esgotado e não possui unidades em estoque."
        )
    else:
        sentences.append(
            f"O estoque atual de {product} é de {stock} "
            f"{pluralize(stock, 'unidade', 'unidades')}."
        )
    sentences.append(
        f"O prazo de envio de {product} é de {shipping_days} "
        f"{pluralize(shipping_days, 'dia útil', 'dias úteis')}."
    )
    sentences.append(
        f"O produto {product} é vendido por {row['vendedor']}, "
        f"em {row['cidade_uf']}, com garantia de {warranty_months} "
        f"{pluralize(warranty_months, 'mês', 'meses')}."
    )
    return " ".join(sentences)


def load_inventory(csv_path: str | Path) -> str:
    """Converte o CSV em um parágrafo por produto."""
    with open(csv_path, encoding="utf-8", newline="") as file:
        blocks = [row_to_text(row) for row in csv.DictReader(file)]
    return unicodedata.normalize("NFC", "\n\n".join(blocks))
