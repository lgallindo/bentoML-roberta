"""A bancada: três modelos pequenos que chamam ferramenta, medidos lado a lado.

Rode com:  just lfm2_tools bancada
(na primeira vez baixa ~2,8 GB de pesos; depois é só CPU)

A pergunta que esta bancada responde NÃO é "qual modelo escreve melhor".
É outra, mais útil:

    quando o modelo NÃO deveria chamar ferramenta nenhuma, ele fica quieto?

Chamar a ferramenta certa na hora certa, os três fazem. O que separa um
modelo de 354M de um de 494M é a disciplina de não chamar nada quando o
usuário só disse "bom dia" -- e é isso que este arquivo mede.
"""

from __future__ import annotations

import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from ferramentas import ESQUEMA, extrair

MODELOS = [
    ("LiquidAI/LFM2-350M", "o menor com tool calling de fábrica"),
    ("Qwen/Qwen2.5-0.5B-Instruct", "+140M parâmetros"),
    ("MadeAgents/Hammer2.1-0.5b", "treinado SÓ para chamar ferramenta"),
]

# (deve_chamar, pergunta, argumento_esperado)
CASOS = [
    (True, "Quantas unidades do Fone de ouvido Bluetooth existem em estoque?", "Fone de ouvido Bluetooth"),
    (True, "Tem Cafeteira elétrica no estoque?", "Cafeteira elétrica"),
    (True, "Quais são os feriados de 2026?", 2026),
    (False, "Bom dia! Tudo bem?", None),
    (False, "Qual é a capital da França?", None),
    (False, "Obrigado, era só isso.", None),
    (False, "Me explique o que é um marketplace.", None),
]


def rodar(nome: str) -> dict:
    """Roda os casos num modelo e devolve o placar."""
    tokenizer = AutoTokenizer.from_pretrained(nome)
    modelo = AutoModelForCausalLM.from_pretrained(nome, dtype=torch.float32)
    modelo.eval()
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    parametros = sum(p.numel() for p in modelo.parameters())
    acertos_decisao = 0
    acertos_argumento = 0
    total_argumentos = 0
    linhas = []
    inicio = time.perf_counter()

    for deve, pergunta, esperado in CASOS:
        texto = tokenizer.apply_chat_template(
            [{"role": "user", "content": pergunta}],
            tools=ESQUEMA,
            tokenize=False,
            add_generation_prompt=True,
        )
        entrada = tokenizer(texto, return_tensors="pt")
        with torch.inference_mode():
            saida = modelo.generate(
                **entrada,
                max_new_tokens=80,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        cru = tokenizer.decode(
            saida[0][entrada["input_ids"].shape[-1]:], skip_special_tokens=False
        ).strip()

        chamadas = extrair(cru)
        chamou = bool(chamadas)
        decisao_ok = chamou == deve
        acertos_decisao += decisao_ok

        argumento = None
        if deve and esperado is not None:
            total_argumentos += 1
            if chamadas:
                valores = list(chamadas[0].get("arguments", {}).values())
                argumento = valores[0] if valores else None
                if str(argumento).strip() == str(esperado).strip():
                    acertos_argumento += 1

        linhas.append(
            {
                "pergunta": pergunta,
                "deve": deve,
                "chamou": chamou,
                "ok": decisao_ok,
                "chamadas": chamadas,
                "argumento": argumento,
                "cru": cru[:110],
            }
        )

    del modelo
    return {
        "modelo": nome,
        "parametros_m": parametros / 1e6,
        "decisao": (acertos_decisao, len(CASOS)),
        "argumentos": (acertos_argumento, total_argumentos),
        "segundos": time.perf_counter() - inicio,
        "linhas": linhas,
    }


def main() -> int:
    resultados = []
    for nome, apelido in MODELOS:
        print(f"\n{'=' * 78}")
        print(f"### {nome}   ({apelido})")
        print("=" * 78)
        resultado = rodar(nome)
        resultados.append(resultado)
        for linha in resultado["linhas"]:
            marca = "OK  " if linha["ok"] else "ERRO"
            esperado = "deve chamar" if linha["deve"] else "NÃO deve chamar"
            print(f"  {marca} {esperado:16} | {linha['pergunta'][:44]:46}")
            if linha["chamadas"]:
                c = linha["chamadas"][0]
                print(f"         -> {c['name']}({c.get('arguments', {})})")
            else:
                print(f"         -> (sem ferramenta) {linha['cru'][:60]!r}")

    print(f"\n{'=' * 78}")
    print("PLACAR")
    print("=" * 78)
    print(f"  {'modelo':32} {'params':>9}  {'decisão':>9}  {'argumentos':>11}  {'tempo':>7}")
    for r in resultados:
        d, dt = r["decisao"]
        a, at = r["argumentos"]
        print(
            f"  {r['modelo']:32} {r['parametros_m']:8.1f}M  {d:>4}/{dt:<4}  "
            f"{a:>6}/{at:<4}  {r['segundos']:6.1f}s"
        )

    print(
        "\n  'decisão'    = acertou em CHAMAR quando devia e em ficar quieto quando não devia\n"
        "  'argumentos' = extraiu o argumento exatamente como o CSV/a API espera\n"
    )
    print(
        "  A leitura: os três sabem chamar. O que o tamanho compra não é a\n"
        "  chamada -- é o bom senso de não chamar.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
